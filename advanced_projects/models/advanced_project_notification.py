from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models

from .advanced_project_options import CLOSED_CATEGORIES

# Which record each event is about (the template renders against it).
EVENT_MODELS = {
    'task_assigned': 'advanced.project.task',
    'task_due_soon': 'advanced.project.task',
    'task_overdue': 'advanced.project.task',
    'task_done': 'advanced.project.task',
    'update_published': 'advanced.project.update',
    'project_stage': 'advanced.project',
}
PROJECT_EVENTS = ('update_published', 'project_stage')


class AdvancedProjectNotification(models.Model):
    """An email sent when something happens on a project.

    Only used while Workflow Automation (``workflow_automation``) is not
    installed: with it, project notifications are set up as workflows
    instead, so the Notification Templates menu is hidden and nothing here is
    sent (the same as Actions' Notification Templates).
    """
    _name = 'advanced.project.notification'
    _description = 'Project Notification Template'
    _inherit = ['mail.render.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: the code that sends notifications depends on these events.
    event = fields.Selection(
        [('task_assigned', 'Task Assigned'), ('task_due_soon', 'Task Due Soon'),
         ('task_overdue', 'Task Overdue'), ('task_done', 'Task Done'),
         ('update_published', 'Project Update Published'), ('project_stage', 'Project Stage Changed')],
        string='Send When', required=True, default='task_assigned',
        help='Task Assigned: to the people a task is assigned to (when it is created or people are added).\n'
             'Task Due Soon: once, the given number of days before the task ends.\n'
             'Task Overdue: once, the day after the task should have ended.\n'
             'Task Done: when the task reaches a Done stage.\n'
             'Project Update Published: when an update is published (followers also get it on the chatter).\n'
             'Project Stage Changed: when the project moves to another stage.',
    )
    days_before = fields.Integer(string='Days Before End', default=1)
    project_type_ids = fields.Many2many(
        'advanced.project.type', string='Only for Project Types',
        help='Leave empty to send this notification for every project.')
    notify_assignees = fields.Boolean(string='Task Assignees', default=True)
    notify_manager = fields.Boolean(string='Project Manager')
    notify_team = fields.Boolean(string='Colleagues on the Team')
    notify_customers = fields.Boolean(
        string='Customers on the Team',
        help='Only for project events, and never for updates kept from customers or internal projects.')
    partner_ids = fields.Many2many('res.partner', string='Also Send To')
    subject = fields.Char(translate=True, required=True)
    body_html = fields.Html(
        string='Body', render_engine='qweb', render_options={'post_process': True},
        translate=True, sanitize='email_outgoing',
    )
    is_project_event = fields.Boolean(compute='_compute_render_model')

    @api.depends('event')
    def _compute_render_model(self):
        for template in self:
            template.render_model = EVENT_MODELS.get(template.event, 'advanced.project.task')
            template.is_project_event = template.event in PROJECT_EVENTS

    @api.model
    def _notifications_enabled(self):
        return not self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'workflow_automation'), ('state', '=', 'installed'),
        ])

    @api.model
    def _send_event(self, event, records, partners_by_record=None):
        """Send this event's templates for ``records`` (tasks, updates or
        projects). ``partners_by_record`` replaces the assignees (e.g. only
        the people just assigned)."""
        if not records or self.env.context.get('advanced_project_no_notify') or not self._notifications_enabled():
            return
        for template in self.sudo().search([('event', '=', event)]):
            for record in records:
                assignees = None
                if partners_by_record is not None:
                    assignees = partners_by_record.get(record)
                    if not assignees:
                        continue
                template._send(record, assignees=assignees)

    def _project_of(self, record):
        return record if record._name == 'advanced.project' else record.project_id

    def _send(self, record, assignees=None):
        self.ensure_one()
        project = self._project_of(record)
        if project.is_template:
            return
        if self.project_type_ids and project.project_type_id not in self.project_type_ids:
            return
        team = project.collaborator_ids
        partners = self.env['res.partner']
        if self.notify_assignees and record._name == 'advanced.project.task':
            partners |= assignees if assignees is not None else record.user_ids.partner_id
        if self.notify_manager:
            partners |= project.user_id.partner_id
        if self.notify_team:
            partners |= team.filtered(lambda c: c.collaborator_type == 'colleague').partner_id
        if self.notify_customers and self.event in PROJECT_EVENTS and not project.is_internal and (
                record._name != 'advanced.project.update' or record.customer_visible):
            partners |= team.filtered(lambda c: c.collaborator_type == 'customer' and c.access_state == 'ok').partner_id
        partners = (partners | self.partner_ids).filtered('email')
        if not partners:
            return
        subject = self._render_field('subject', record.ids)[record.id]
        body = self._render_field('body_html', record.ids)[record.id]
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'body': Markup(body),
            'recipient_ids': [(6, 0, partners.ids)],
            'model': record._name,
            'res_id': record.id,
            'email_from': project.company_id.email_formatted or self.env.user.email_formatted,
            'author_id': self.env.user.partner_id.id,
            'auto_delete': True,
        })

    @api.model
    def _cron_notify_deadlines(self):
        """Daily: Task Due Soon and Task Overdue, once per task."""
        if not self._notifications_enabled():
            return
        Task = self.env['advanced.project.task'].sudo()
        today = fields.Date.context_today(self)
        base = [('stage_category', 'not in', CLOSED_CATEGORIES), ('is_template', '=', False),
                ('project_id.active', '=', True)]
        overdue = Task.search(base + [('date_end', '<', today), ('overdue_notified', '=', False)])
        self._send_event('task_overdue', overdue)
        overdue.write({'overdue_notified': True})
        for template in self.sudo().search([('event', '=', 'task_due_soon')]):
            due_soon = Task.search(base + [
                ('due_soon_notified', '=', False), ('date_end', '>=', today),
                ('date_end', '<=', today + timedelta(days=template.days_before)),
            ])
            for task in due_soon:
                template._send(task)
            due_soon.write({'due_soon_notified': True})


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        # Project Notification Templates are managed by Workflow Automation when it is installed.
        visible = super()._visible_menu_ids(debug=debug)
        menu = self.env.ref('advanced_projects.menu_advanced_projects_notification', raise_if_not_found=False)
        if menu and menu.id in visible and not self.env['advanced.project.notification']._notifications_enabled():
            visible = type(visible)(set(visible) - {menu.id})
        return visible

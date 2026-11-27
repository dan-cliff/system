from markupsafe import Markup

from odoo import api, fields, models


class AdvancedActionNotification(models.Model):
    """An email sent when something happens to an action.

    Only used while Workflow Automation (``workflow_automation``) is not
    installed: with it, notifications are set up as workflows instead, so
    this menu is hidden and nothing here is sent.
    """
    _name = 'advanced.action.notification'
    _description = 'Action Notification Template'
    _inherit = ['mail.render.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: the code that sends notifications depends on these events.
    event = fields.Selection(
        [('assigned', 'Assigned'), ('due_soon', 'Due Soon'), ('overdue', 'Overdue'),
         ('done', 'Done'), ('cancelled', 'Cancelled')],
        string='Send When', required=True, default='assigned',
        help='Assigned: to the users an action is assigned to (when it is created or users are added).\n'
             'Due Soon: once, the given number of days before the action is due.\n'
             'Overdue: once, the day after the action was due.\n'
             'Done / Cancelled: when the action is marked Done or Cancelled.',
    )
    days_before = fields.Integer(string='Days Before Due', default=1)
    source_app = fields.Selection(
        selection='_selection_source_app', string='Only for App',
        help='Leave empty to send this notification for the actions of every app.',
    )
    notify_assignees = fields.Boolean(string='Assigned Users', default=True)
    notify_creator = fields.Boolean(string='Creator')
    partner_ids = fields.Many2many('res.partner', string='Also Send To')
    subject = fields.Char(translate=True, required=True)
    body_html = fields.Html(
        string='Body', render_engine='qweb', render_options={'post_process': True},
        translate=True, sanitize='email_outgoing',
    )

    def _compute_render_model(self):
        self.render_model = 'advanced.action'

    @api.model
    def _selection_source_app(self):
        return self.env['advanced.action']._fields['source_app']._description_selection(self.env)

    @api.model
    def _notifications_enabled(self):
        return not self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'workflow_automation'), ('state', '=', 'installed'),
        ])

    def _send(self, action, assignees=None):
        """Email this notification about ``action``. ``assignees`` replaces
        the action's assigned users (e.g. only the users just added)."""
        self.ensure_one()
        if self.source_app and action.source_app != self.source_app:
            return
        partners = self.env['res.partner']
        if self.notify_assignees:
            partners |= assignees if assignees is not None else action.user_ids.partner_id
        if self.notify_creator:
            partners |= action.create_uid.partner_id
        partners = (partners | self.partner_ids).filtered('email')
        if not partners:
            return
        subject = self._render_field('subject', action.ids)[action.id]
        body = self._render_field('body_html', action.ids)[action.id]
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'body': Markup(body),
            'recipient_ids': [(6, 0, partners.ids)],
            'model': 'advanced.action',
            'res_id': action.id,
            'email_from': action.company_id.email_formatted or self.env.user.email_formatted,
            'author_id': self.env.user.partner_id.id,
            'auto_delete': True,
        })

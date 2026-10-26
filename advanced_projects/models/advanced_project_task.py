from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .advanced_project_options import CLOSED_CATEGORIES


class AdvancedProjectTask(models.Model):
    _name = 'advanced.project.task'
    _description = 'Project Task'
    _inherit = ['portal.mixin', 'advanced.project.private.chatter.mixin', 'mail.activity.mixin']
    _order = 'sequence, date_start, id'
    _mail_post_access = 'read'  # customers comment through the portal

    @api.model
    def _default_stage_id(self):
        return self.env['advanced.project.task.stage'].search([], limit=1)

    name = fields.Char('Title', required=True, tracking=True, index='trigram')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color Index')
    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade', tracking=True)
    is_template = fields.Boolean(related='project_id.is_template', store=True, string='In a Template')
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    phase_id = fields.Many2one(
        'advanced.project.phase', string='Phase', index=True, tracking=True, ondelete='set null',
        domain="[('project_id', '=', project_id)]")
    stage_id = fields.Many2one(
        'advanced.project.task.stage', string='Stage', required=True, index=True, tracking=True,
        ondelete='restrict', default=_default_stage_id, group_expand='_read_group_stage_ids', copy=False)
    stage_category = fields.Selection(related='stage_id.category', store=True, string='Stage Category')
    user_ids = fields.Many2many(
        'res.users', 'advanced_project_task_user_rel', 'task_id', 'user_id', string='Assignees',
        tracking=True, domain="[('share', '=', False)]")
    date_start = fields.Date('Start Date', tracking=True, index=True)
    date_end = fields.Date('End Date', tracking=True, index=True)
    duration = fields.Integer('Duration (days)', compute='_compute_duration')
    date_done = fields.Datetime(
        'Completed On', compute='_compute_date_done', store=True, readonly=True, copy=False, index=True)
    planned_hours = fields.Float('Allocated Hours')
    is_milestone = fields.Boolean('Milestone', tracking=True)
    customer_visible = fields.Boolean(
        'Visible to Customers', default=True,
        help="Customers on the project's team see this task in the portal.")
    is_overdue = fields.Boolean('Overdue', compute='_compute_is_overdue', search='_search_is_overdue')
    description = fields.Html()
    tag_ids = fields.Many2many('advanced.project.tag', string='Tags')
    parent_ids = fields.Many2many(
        'advanced.project.task', 'advanced_project_task_link_rel', 'child_id', 'parent_id',
        string='Parent Tasks', domain="[('project_id', '=', project_id), ('id', '!=', id)]",
        help='Tasks this task sits under (or follows). A task can have several parents.')
    child_ids = fields.Many2many(
        'advanced.project.task', 'advanced_project_task_link_rel', 'parent_id', 'child_id',
        string='Child Tasks', domain="[('project_id', '=', project_id), ('id', '!=', id)]",
        help='Tasks under (or following) this task. A task can have several children.')
    parent_count = fields.Integer(compute='_compute_link_counts')
    child_count = fields.Integer(compute='_compute_link_counts')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([])

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for task in self:
            if task.date_start and task.date_end:
                task.duration = (task.date_end - task.date_start).days + 1
            else:
                task.duration = 1 if (task.date_start or task.date_end) else 0

    @api.depends('stage_category')
    def _compute_date_done(self):
        # set when the task reaches a Done stage, cleared when it leaves it
        now = fields.Datetime.now()
        for task in self:
            task.date_done = (task.date_done or now) if task.stage_category == 'done' else False

    @api.depends('date_end', 'stage_category')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for task in self:
            task.is_overdue = bool(task.date_end and task.date_end < today
                                   and task.stage_category not in CLOSED_CATEGORIES)

    def _search_is_overdue(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        today = fields.Date.context_today(self)
        overdue = ['&', ('date_end', '<', today), ('stage_category', 'not in', CLOSED_CATEGORIES)]
        positive = (operator == 'in') == (True in value)
        return overdue if positive else ['!'] + overdue

    @api.depends('parent_ids', 'child_ids')
    def _compute_link_counts(self):
        for task in self:
            task.parent_count = len(task.parent_ids)
            task.child_count = len(task.child_ids)

    def _compute_access_url(self):
        super()._compute_access_url()
        for task in self:
            task.access_url = f'/my/projects/{task.project_id.id}/tasks/{task.id}'

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for task in self:
            if task.date_start and task.date_end and task.date_end < task.date_start:
                raise ValidationError(_('"%s" ends before it starts.', task.name))

    @api.constrains('phase_id', 'project_id')
    def _check_phase(self):
        for task in self:
            if task.phase_id and task.phase_id.project_id != task.project_id:
                raise ValidationError(_('The phase of "%s" belongs to another project.', task.name))

    @api.constrains('parent_ids', 'child_ids')
    def _check_links(self):
        for task in self:
            linked = task.parent_ids | task.child_ids
            if task in linked:
                raise ValidationError(_('"%s" cannot be linked to itself.', task.name))
            if linked.filtered(lambda t: t.project_id != task.project_id):
                raise ValidationError(_('"%s" can only be linked to tasks of the same project.', task.name))
        if self._has_cycle('child_ids'):
            raise ValidationError(_('Tasks cannot be linked in a loop (a task cannot sit under its own child).'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.phase_id and self.phase_id.project_id != self.project_id:
            self.phase_id = False

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.filtered('user_ids')._add_assignees_to_team()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if vals.get('user_ids'):
            self._add_assignees_to_team()
        return res

    def _add_assignees_to_team(self):
        """Assignees join the project's team as Colleagues."""
        Collaborator = self.env['advanced.project.collaborator']
        for project in self.project_id:
            on_team = project.collaborator_ids.partner_id
            partners = self.filtered(lambda t: t.project_id == project).user_ids.partner_id - on_team
            if partners:
                Collaborator.create([{
                    'project_id': project.id, 'partner_id': partner.id, 'collaborator_type': 'colleague',
                } for partner in partners])

    def action_open_project(self):
        self.ensure_one()
        return self.project_id.action_open_project()

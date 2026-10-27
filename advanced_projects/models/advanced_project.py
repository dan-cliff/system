from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .advanced_project_options import CLOSED_CATEGORIES


class AdvancedProject(models.Model):
    _name = 'advanced.project'
    _description = 'Project'
    _inherit = ['portal.mixin', 'advanced.project.private.chatter.mixin', 'mail.activity.mixin']
    _order = 'sequence, id desc'
    _mail_post_access = 'read'  # customers comment through the portal
    _org_form_company = True

    @api.model
    def _default_project_type(self):
        Type = self.env['advanced.project.type']
        if 'default_is_internal' in self.env.context:
            return Type.search([('is_internal', '=', bool(self.env.context['default_is_internal']))], limit=1)
        return Type.search([('is_internal', '=', False)], limit=1) or Type.search([], limit=1)

    def _default_stage_id(self):
        return self.env['advanced.project.stage'].search([], limit=1)

    name = fields.Char(required=True, tracking=True, index='trigram')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color Index')
    description = fields.Html()
    is_template = fields.Boolean(
        'Template', copy=False, index=True,
        help='Templates are listed under Configuration and used to start new projects with their plan.')
    template_id = fields.Many2one(
        'advanced.project', string='Created From', copy=False, readonly=True, index='btree_not_null',
        ondelete='set null')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, tracking=True,
        default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Project Manager', tracking=True, index=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True, index=True)
    project_type_id = fields.Many2one(
        'advanced.project.type', string='Project Type', tracking=True, index=True, ondelete='restrict',
        default=lambda self: self._default_project_type(),
        help='Internal projects are run for the company itself; external projects for a customer.')
    is_internal = fields.Boolean(
        related='project_type_id.is_internal', string='Internal Project', store=True, index=True)
    stage_id = fields.Many2one(
        'advanced.project.stage', string='Stage', tracking=True, index=True, ondelete='restrict',
        default=_default_stage_id, group_expand='_read_group_stage_ids', copy=False)
    is_closed = fields.Boolean(related='stage_id.is_closed', string='Closed', store=True)
    status_id = fields.Many2one(
        'advanced.project.status', string='Status', tracking=True, index=True, ondelete='restrict',
        copy=False, help="The project's health, set by hand or by the latest published Project Update.")
    status_color = fields.Char(related='status_id.color')
    tag_ids = fields.Many2many('advanced.project.tag', string='Tags')
    date_start = fields.Date('Start Date', default=fields.Date.context_today, tracking=True)
    date_end = fields.Date('Target End Date', tracking=True)

    phase_ids = fields.One2many('advanced.project.phase', 'project_id', string='Phases', copy=False)
    task_ids = fields.One2many('advanced.project.task', 'project_id', string='Tasks', copy=False)
    collaborator_ids = fields.One2many(
        'advanced.project.collaborator', 'project_id', string='Team', copy=False)
    update_ids = fields.One2many('advanced.project.update', 'project_id', string='Project Updates', copy=False)

    task_count = fields.Integer('Task Count', compute='_compute_task_stats')
    open_task_count = fields.Integer('Open Tasks', compute='_compute_task_stats')
    progress = fields.Float(
        'Progress', compute='_compute_progress', store=True, aggregator='avg',
        help='Share of tasks done (cancelled tasks are left out).')
    update_count = fields.Integer('Updates', compute='_compute_update_count')
    collaborator_count = fields.Integer('Team Members', compute='_compute_collaborator_count')
    customer_partner_ids = fields.Many2many(
        'res.partner', string='Customers', compute='_compute_collaborator_partners')
    access_issue_count = fields.Integer(
        'Access Issues', compute='_compute_collaborator_partners',
        help='Customers on the team who cannot open the project yet.')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([])

    @api.depends('task_ids.stage_category', 'task_ids.active')
    def _compute_progress(self):
        for project in self:
            tasks = project.task_ids.filtered(lambda t: t.stage_category != 'cancelled')
            done = tasks.filtered(lambda t: t.stage_category == 'done')
            project.progress = 100.0 * len(done) / len(tasks) if tasks else 0.0

    def _compute_task_stats(self):
        Task = self.env['advanced.project.task']
        totals = dict(Task._read_group([('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        opened = dict(Task._read_group(
            [('project_id', 'in', self.ids), ('stage_category', 'not in', CLOSED_CATEGORIES)],
            ['project_id'], ['__count']))
        for project in self:
            project.task_count = totals.get(project, 0)
            project.open_task_count = opened.get(project, 0)

    def _compute_update_count(self):
        counts = dict(self.env['advanced.project.update']._read_group(
            [('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        for project in self:
            project.update_count = counts.get(project, 0)

    def _compute_collaborator_count(self):
        counts = dict(self.env['advanced.project.collaborator']._read_group(
            [('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        for project in self:
            project.collaborator_count = counts.get(project, 0)

    @api.depends('collaborator_ids.partner_id', 'collaborator_ids.collaborator_type')
    def _compute_collaborator_partners(self):
        for project in self:
            customers = project.collaborator_ids.filtered(lambda c: c.collaborator_type == 'customer')
            project.customer_partner_ids = customers.partner_id
            project.access_issue_count = len(customers.filtered(lambda c: c.access_state != 'ok'))

    def _compute_access_url(self):
        super()._compute_access_url()
        for project in self:
            project.access_url = f'/my/projects/{project.id}'

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        for project in projects:
            project._add_manager_to_team()
        return projects

    def write(self, vals):
        stages_before = {project: project.stage_id for project in self} if 'stage_id' in vals else {}
        res = super().write(vals)
        if vals.get('user_id'):
            for project in self:
                project._add_manager_to_team()
        if stages_before:
            self.env['advanced.project.notification']._send_event(
                'project_stage', self.filtered(lambda p: p.stage_id != stages_before[p]))
        return res

    def copy(self, default=None):
        new_projects = super().copy(default)
        for source, project in zip(self, new_projects):
            project._copy_plan_from(source)
        return new_projects

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if 'name' not in (default or {}):
            for project, vals in zip(self, vals_list):
                vals['name'] = _('%s (copy)', project.name)
        return vals_list

    def _add_manager_to_team(self):
        self.ensure_one()
        partner = self.user_id.partner_id
        if partner and partner not in self.collaborator_ids.partner_id:
            self.env['advanced.project.collaborator'].create({
                'project_id': self.id, 'partner_id': partner.id, 'collaborator_type': 'colleague',
            })

    def _copy_plan_from(self, source, day_shift=0):
        """Copy the phases and tasks (with their links) of
        ``source`` into this project, moving every date by ``day_shift`` days.
        The source is read as superuser so anyone allowed to create projects
        can start from a template; the copies are created as the user."""
        self.ensure_one()
        source = source.sudo()

        def shift(date):
            return date + timedelta(days=day_shift) if date else False

        Phase = self.env['advanced.project.phase']
        Task = self.env['advanced.project.task']
        first_stage = Task._default_stage_id()
        phase_map = {}
        for phase in source.phase_ids:
            phase_map[phase.id] = Phase.create({
                'project_id': self.id, 'name': phase.name, 'sequence': phase.sequence,
                'description': phase.description, 'color': phase.color,
            })
        tasks = source.task_ids
        new_tasks = Task.create([{
            'project_id': self.id,
            'name': task.name,
            'sequence': task.sequence,
            'phase_id': phase_map[task.phase_id.id].id if task.phase_id else False,
            'stage_id': first_stage.id,
            'description': task.description,
            'date_start': shift(task.date_start),
            'date_end': shift(task.date_end),
            'is_milestone': task.is_milestone,
            'customer_visible': task.customer_visible,
            'tag_ids': [(6, 0, task.tag_ids.ids)],
            'user_ids': [(6, 0, task.user_ids.filtered('active').ids)],
            'planned_hours': task.planned_hours,
        } for task in tasks])
        task_map = dict(zip(tasks.ids, new_tasks))
        for task in tasks.filtered('child_ids'):
            children = [task_map[child.id].id for child in task.child_ids if child.id in task_map]
            if children:
                task_map[task.id].child_ids = [(6, 0, children)]
        # each link keeps its kind (End to Start, Start to Start, ...)
        new_links = {(link.parent_id.id, link.child_id.id): link for link in new_tasks.sudo().child_link_ids}
        for link in tasks.child_link_ids:
            parent, child = task_map.get(link.parent_id.id), task_map.get(link.child_id.id)
            new_link = parent and child and new_links.get((parent.id, child.id))
            if new_link and new_link.link_type != link.link_type:
                new_link.link_type = link.link_type

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_open_tasks(self, view_type='kanban', domain=None, name=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_projects.advanced_project_task_action')
        views = {
            'kanban': self.env.ref('advanced_projects.advanced_project_task_view_kanban').id,
            'list': self.env.ref('advanced_projects.advanced_project_task_view_list').id,
            'project_gantt': self.env.ref('advanced_projects.advanced_project_task_view_gantt').id,
        }
        order = [view_type] + [v for v in ('kanban', 'list', 'project_gantt') if v != view_type]
        action.update({
            'name': name or _('%s – Tasks', self.name),
            'domain': [('project_id', '=', self.id)] + (domain or []),
            'views': [(views[v], v) for v in order] + [(False, 'form')],
            'context': {'default_project_id': self.id, 'active_id': self.id},
        })
        return action

    def action_open_tasks_list(self):
        return self.action_open_tasks('list')

    def action_open_gantt(self):
        return self.action_open_tasks('project_gantt')

    def action_open_updates(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_projects.advanced_project_update_action')
        action.update({
            'name': _('%s – Project Updates', self.name),
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        })
        return action

    def action_open_team(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'advanced_projects.advanced_project_collaborator_action')
        action.update({
            'name': _('%s – Team', self.name),
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        })
        return action

    def action_open_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'name': self.name,
        }

    def action_invite(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invite to %s', self.name),
            'res_model': 'advanced.project.invite',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_project_id': self.id},
        }

    def action_new_from_template(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Project from a Template'),
            'res_model': 'advanced.project.from.template',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_id': self.id if len(self) == 1 and self.is_template else False},
        }

    def action_save_as_template(self):
        self.ensure_one()
        if not self.env.user.has_group('advanced_projects.group_advanced_project_manager'):
            raise AccessError(_('Only Project Administrators can create project templates.'))
        template = self.copy({
            'name': _('%s (Template)', self.name), 'partner_id': False,
        })
        template.is_template = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': template.id,
            'views': [(False, 'form')],
            'name': template.name,
        }

    # ------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------

    def _create_from_template(self, vals):
        """Start a project from this template: ``vals`` holds the new project's
        own values (name, customer, start date, ...)."""
        self.ensure_one()
        template = self.sudo()
        if not template.is_template:
            raise UserError(_('%s is not a project template.', template.name))
        vals = dict(vals)
        vals.setdefault('name', template.name)
        vals.setdefault('description', template.description)
        vals.setdefault('tag_ids', [(6, 0, template.tag_ids.ids)])
        if template.project_type_id:
            vals.setdefault('project_type_id', template.project_type_id.id)
        vals['template_id'] = template.id
        start = fields.Date.to_date(vals.get('date_start')) or fields.Date.context_today(self)
        vals['date_start'] = start
        day_shift = (start - template.date_start).days if template.date_start else 0
        if template.date_end and 'date_end' not in vals:
            vals['date_end'] = template.date_end + timedelta(days=day_shift)
        project = self.create(vals)
        project._copy_plan_from(template, day_shift=day_shift)
        return project

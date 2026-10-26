from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .advanced_project_task_filter import format_date

PUBLISH_GROUP = 'advanced_projects.group_advanced_project_update_publish'

# Blocks a Project Update is built from: text, or a task widget. The editor
# draws each kind with its own code, so this stays a fixed selection.
BLOCK_TYPES = [
    ('text', 'Text'),
    ('tasks', 'Task Widget'),
]

# What a new update starts with: (block type, title, task filter, days).
DEFAULT_BLOCKS = [
    ('text', 'Highlights', False, 0),
    ('tasks', 'Completed', 'completed', 14),
    ('tasks', 'Upcoming', 'upcoming', 14),
    ('tasks', 'Blocked', 'blocked', 0),
]


class AdvancedProjectUpdate(models.Model):
    _name = 'advanced.project.update'
    _description = 'Project Update'
    _inherit = ['portal.mixin', 'advanced.project.private.chatter.mixin', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _mail_post_access = 'read'  # customers comment through the portal

    def _default_name(self):
        return _('Project Update – %s', format_date(fields.Date.context_today(self)))

    name = fields.Char('Title', required=True, default=_default_name, tracking=True)
    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade', tracking=True)
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Author', default=lambda self: self.env.user, tracking=True,
        domain="[('share', '=', False)]")
    status_id = fields.Many2one(
        'advanced.project.status', string='Project Status', tracking=True, ondelete='restrict',
        help="The project's health as of this update; publishing sets it on the project.")
    status_color = fields.Char(related='status_id.color')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
    ], default='draft', required=True, tracking=True, copy=False, index=True)
    customer_visible = fields.Boolean(
        'Share with Customers', default=True,
        help='Customers on the project see the update in the portal once it is published.')
    summary = fields.Text(help='A line or two shown on the Overview and in lists.')
    block_ids = fields.One2many('advanced.project.update.block', 'update_id', string='Content', copy=True)
    body_html = fields.Html(
        'Published Content', readonly=True, copy=False, sanitize_style=True,
        help='The update as published, with its task lists frozen at that moment.')
    published_date = fields.Datetime('Published On', readonly=True, copy=False)
    can_publish = fields.Boolean(compute='_compute_can_publish')

    def _compute_can_publish(self):
        allowed = self.env.user.has_group(PUBLISH_GROUP)
        for update in self:
            update.can_publish = allowed

    def _compute_access_url(self):
        super()._compute_access_url()
        for update in self:
            update.access_url = f'/my/projects/{update.project_id.id}/updates/{update.id}'

    @api.model_create_multi
    def create(self, vals_list):
        updates = super().create(vals_list)
        Block = self.env['advanced.project.update.block']
        block_vals = []
        for update, vals in zip(updates, vals_list):
            if 'block_ids' in vals or self.env.context.get('advanced_project_update_empty'):
                continue
            if not update.status_id:
                update.status_id = update.project_id.status_id
            for sequence, (block_type, title, task_filter, days) in enumerate(DEFAULT_BLOCKS):
                vals = {'update_id': update.id, 'sequence': sequence * 10, 'block_type': block_type,
                        'title': title}
                if task_filter:
                    vals.update(task_filter=task_filter, days=days)
                block_vals.append(vals)
        if block_vals:
            Block.create(block_vals)
        return updates

    # ------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------

    def get_editor_data(self):
        """The update's blocks with their live task lists, plus the choices
        the task widgets' filters offer (the project's phases and people)."""
        self.ensure_one()
        self.check_access('read')
        project = self.project_id
        Block = self.env['advanced.project.update.block']
        users = (project.task_ids.user_ids | project.collaborator_ids.user_id).filtered(
            lambda u: u.active and not u.share)
        return {
            'id': self.id,
            'state': self.state,
            'can_edit': self.state == 'draft' and self.has_access('write'),
            'blocks': [block._editor_values() for block in self.block_ids],
            'phases': [{'id': p.id, 'name': p.name} for p in project.phase_ids],
            'users': [{'id': u.id, 'name': u.name} for u in users.sorted('name')],
            'task_filters': [{'value': value, 'label': label} for value, label in
                             Block._fields['task_filter']._description_selection(self.env)],
            'palette': Block._palette(),
        }

    def editor_add_block(self, block_type, task_filter=False, index=None):
        """Add a block (dropped from the palette at ``index``, or at the end)."""
        self.ensure_one()
        self._check_draft()
        Block = self.env['advanced.project.update.block']
        vals = {'update_id': self.id, 'block_type': block_type}
        if block_type == 'tasks':
            task_filter = task_filter or 'outstanding'
            labels = dict(Block._fields['task_filter']._description_selection(self.env))
            vals.update(task_filter=task_filter, title=labels.get(task_filter, ''),
                        days=14 if task_filter in ('upcoming', 'completed') else 0)
        block = Block.create(vals)
        blocks = self.block_ids - block
        order = blocks.ids
        order.insert(len(order) if index is None else max(0, min(index, len(order))), block.id)
        self.editor_resequence(order)
        return block._editor_values()

    def editor_resequence(self, block_ids):
        self.ensure_one()
        self._check_draft()
        blocks = self.block_ids
        for sequence, block_id in enumerate(block_ids):
            block = blocks.filtered(lambda b: b.id == block_id)
            if block and block.sequence != sequence * 10:
                block.sequence = sequence * 10
        self.invalidate_recordset(['block_ids'])
        return True

    def _check_draft(self):
        for update in self:
            if update.state != 'draft':
                raise UserError(_('"%s" is published: set it back to draft to change it.', update.name))

    # ------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------

    def _check_publish_rights(self):
        if not self.env.user.has_group(PUBLISH_GROUP):
            raise AccessError(_('You need the "Project Updates: Publish" permission to publish or '
                                'unpublish Project Updates.'))
        self.check_access('read')

    def action_publish(self):
        self._check_publish_rights()
        for update in self:
            if update.state == 'published':
                continue
            # sudo: workflow action checked above (CLAUDE.md > Permissions)
            update_sudo = update.sudo()
            for block in update_sudo.block_ids.filtered(lambda b: b.block_type == 'tasks'):
                block.snapshot_html = block._render_tasks_html()
            update_sudo.write({
                'state': 'published',
                'published_date': fields.Datetime.now(),
                'body_html': update_sudo._render_document(),
            })
            if update.status_id:
                update_sudo.project_id.status_id = update.status_id
            update._post_to_project()
        return True

    def action_reset_draft(self):
        self._check_publish_rights()
        # sudo: workflow action checked above
        self.sudo().write({'state': 'draft', 'body_html': False, 'published_date': False})
        self.sudo().block_ids.write({'snapshot_html': False})
        return True

    def _render_document(self):
        self.ensure_one()
        return self.env['ir.qweb']._render('advanced_projects.update_document', {
            'update': self, 'format_date': format_date,
        })

    def _post_to_project(self):
        """Share the published update on the project's chatter (a short summary
        and a link to the full update): customers who follow the project hear
        about it unless it is kept internal."""
        self.ensure_one()
        body = self.env['ir.qweb']._render('advanced_projects.update_chatter_summary', {
            'update': self,
            'url': f'{self.get_base_url()}{self.access_url}',
            'sections': [(block.title, block._get_tasks()[1])
                         for block in self.block_ids.filtered(lambda b: b.block_type == 'tasks')],
        })
        self.project_id.with_context(mail_post_autofollow=False).message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='advanced_projects.mt_project_update_published',
            is_internal=not self.customer_visible,
        )

    def action_open_project(self):
        self.ensure_one()
        return self.project_id.action_open_project()

    def action_preview(self):
        """The update as customers see it in the portal."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.get_portal_url(), 'target': 'new'}


class AdvancedProjectUpdateBlock(models.Model):
    _name = 'advanced.project.update.block'
    _description = 'Project Update Block'
    _inherit = ['advanced.project.task.filter.mixin']
    _order = 'sequence, id'

    update_id = fields.Many2one(
        'advanced.project.update', string='Project Update', required=True, index=True, ondelete='cascade')
    project_id = fields.Many2one(related='update_id.project_id', string='Project')
    company_id = fields.Many2one(related='update_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    block_type = fields.Selection(BLOCK_TYPES, string='Type', required=True, default='text')
    title = fields.Char()
    body = fields.Html('Text')
    snapshot_html = fields.Html(
        'Published Tasks', readonly=True, copy=False, sanitize_style=True,
        help='The task list as it was when the update was published.')

    def _filter_project(self):
        return self.update_id.project_id

    @api.model
    def _palette(self):
        labels = dict(self._fields['task_filter']._description_selection(self.env))
        palette = [{'block_type': 'text', 'task_filter': False, 'label': _('Text'), 'icon': 'fa-align-left'}]
        icons = {'outstanding': 'fa-circle-o', 'upcoming': 'fa-calendar', 'completed': 'fa-check-circle',
                 'blocked': 'fa-ban', 'overdue': 'fa-exclamation-triangle', 'milestones': 'fa-flag',
                 'all': 'fa-list'}
        for value, label in labels.items():
            palette.append({'block_type': 'tasks', 'task_filter': value, 'icon': icons.get(value, 'fa-tasks'),
                            'label': _('%s Tasks', label)})
        return palette

    def _editor_values(self):
        self.ensure_one()
        values = {
            'id': self.id,
            'block_type': self.block_type,
            'title': self.title or '',
            'body': self.body or '',
        }
        if self.block_type == 'tasks':
            values.update(self._filter_values())
            if self.update_id.state == 'published':
                values['snapshot_html'] = self.snapshot_html or ''
        return values

    def get_editor_values(self):
        return [block._editor_values() for block in self]

    def _render_tasks_html(self):
        self.ensure_one()
        tasks, total = self._get_tasks()
        return self.env['ir.qweb']._render('advanced_projects.update_block_tasks', {
            'block': self, 'rows': self._task_rows(tasks), 'total': total,
        })

    @api.model_create_multi
    def create(self, vals_list):
        self.env['advanced.project.update'].browse(
            [vals['update_id'] for vals in vals_list if vals.get('update_id')])._check_draft()
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {'snapshot_html', 'sequence'}:
            self.update_id._check_draft()
        return super().write(vals)

    def unlink(self):
        self.update_id._check_draft()
        return super().unlink()

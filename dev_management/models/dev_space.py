"""Documentation (like Confluence): spaces holding a tree of pages.

Pages are written in the collaborative HTML editor, start from page templates,
keep their full history (each change of the body saves the previous version,
which can be restored) and can be linked to releases, features and tickets.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import is_html_empty

# Saves made by the same person within this many minutes update one version
# instead of each adding a new one.
VERSION_MERGE_MINUTES = 10


class DevSpace(models.Model):
    _name = 'dev.space'
    _description = 'Documentation Space'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    key = fields.Char('Space Key', help='A short code, e.g. DEV or OPS.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    description = fields.Text()
    user_id = fields.Many2one('res.users', 'Owner', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    repository_id = fields.Many2one('dev.repository', 'Repository',
                                    help='The repository this space documents, if any.')
    page_ids = fields.One2many('dev.page', 'space_id', string='Pages')
    page_count = fields.Integer('Page Count', compute='_compute_page_count')
    home_page_id = fields.Many2one('dev.page', 'Home Page', domain="[('space_id', '=', id)]")

    def _compute_page_count(self):
        counts = dict(self.env['dev.page']._read_group([('space_id', 'in', self.ids)], ['space_id'], ['__count']))
        for space in self:
            space.page_count = counts.get(space, 0)

    def action_open_pages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_page_action')
        action.update(name=self.name, domain=[('space_id', '=', self.id)],
                      context={'default_space_id': self.id, 'search_default_top_level': 1})
        return action

    def action_open_home(self):
        self.ensure_one()
        if not self.home_page_id:
            return self.action_open_pages()
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.page', 'res_id': self.home_page_id.id,
                'view_mode': 'form'}


class DevPage(models.Model):
    _name = 'dev.page'
    _description = 'Documentation Page'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _parent_store = True
    _order = 'space_id, parent_path, sequence, id'

    name = fields.Char('Title', required=True, tracking=True)
    space_id = fields.Many2one('dev.space', 'Space', required=True, ondelete='cascade', index=True, tracking=True)
    parent_id = fields.Many2one('dev.page', 'Parent Page', ondelete='cascade', index=True, tracking=True,
                                domain="[('space_id', '=', space_id), ('id', '!=', id)]")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('dev.page', 'parent_id', string='Child Pages')
    child_count = fields.Integer(compute='_compute_child_count')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    body = fields.Html(sanitize_style=True)
    template_id = fields.Many2one('dev.page.template', 'Template', copy=False,
                                  help='Fills the page with the template when the page is still empty.')
    user_id = fields.Many2one('res.users', 'Owner', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    company_id = fields.Many2one(related='space_id.company_id', store=True)
    tag_ids = fields.Many2many('dev.tag', 'dev_page_tag_rel', 'page_id', 'tag_id', string='Labels')
    release_id = fields.Many2one('dev.release', 'Release', index='btree_not_null', tracking=True)
    feature_ids = fields.Many2many('dev.feature', 'dev_page_feature_rel', 'page_id', 'feature_id',
                                   string='Features')
    ticket_ids = fields.Many2many('dev.ticket', 'dev_page_ticket_rel', 'page_id', 'ticket_id', string='Tickets')
    version_ids = fields.One2many('dev.page.version', 'page_id', string='History')
    version_count = fields.Integer('Versions', compute='_compute_version_count')
    last_editor_id = fields.Many2one('res.users', 'Last Edited By', readonly=True, copy=False)
    date_edited = fields.Datetime('Last Edited', readonly=True, copy=False)
    breadcrumb = fields.Char('Path', compute='_compute_breadcrumb', recursive=True)

    @api.depends('child_ids')
    def _compute_child_count(self):
        for page in self:
            page.child_count = len(page.child_ids)

    def _compute_version_count(self):
        counts = dict(self.env['dev.page.version']._read_group([('page_id', 'in', self.ids)], ['page_id'],
                                                                ['__count']))
        for page in self:
            page.version_count = counts.get(page, 0)

    @api.depends('name', 'parent_id.breadcrumb', 'space_id.name')
    def _compute_breadcrumb(self):
        for page in self:
            if page.parent_id:
                page.breadcrumb = '%s / %s' % (page.parent_id.breadcrumb, page.parent_id.name)
            else:
                page.breadcrumb = page.space_id.name or ''

    @api.constrains('parent_id', 'space_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError(_('A page cannot be placed under itself or one of its child pages.'))
        for page in self:
            if page.parent_id and page.parent_id.space_id != page.space_id:
                raise ValidationError(_('A page and its parent page must be in the same space.'))

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and is_html_empty(self.body):
            self.body = self.template_id.body

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            self.space_id = self.parent_id.space_id

    @api.model_create_multi
    def create(self, vals_list):
        templates = self.env['dev.page.template']
        for vals in vals_list:
            if vals.get('template_id') and not vals.get('body'):
                vals['body'] = templates.browse(vals['template_id']).body
            if vals.get('parent_id') and not vals.get('space_id'):
                vals['space_id'] = self.browse(vals['parent_id']).space_id.id
            vals.setdefault('last_editor_id', self.env.uid)
            vals.setdefault('date_edited', fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        if 'body' in vals and not self.env.context.get('dev_page_no_version'):
            self._save_versions()
            vals.setdefault('last_editor_id', self.env.uid)
            vals.setdefault('date_edited', fields.Datetime.now())
        return super().write(vals)

    def _save_versions(self):
        """Keep the current body as a version before it is replaced."""
        Version = self.env['dev.page.version'].sudo()
        now = fields.Datetime.now()
        for page in self:
            if not page.body:
                continue
            recent = page.date_edited and page.last_editor_id.id == self.env.uid and \
                (now - page.date_edited).total_seconds() < VERSION_MERGE_MINUTES * 60
            if recent and page.version_ids:
                # Continuous editing by the same person: keep the version from before they started.
                continue
            Version.create({
                'page_id': page.id,
                'name': page.name,
                'body': page.body,
                'author_id': (page.last_editor_id or page.create_uid).id,
                'date': page.date_edited or page.create_date,
            })

    def action_open_children(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_page_action')
        action.update(name=self.name, domain=[('parent_id', '=', self.id)],
                      context={'default_parent_id': self.id, 'default_space_id': self.space_id.id})
        return action

    def action_open_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('History of %s', self.name),
            'res_model': 'dev.page.version',
            'view_mode': 'list,form',
            'domain': [('page_id', '=', self.id)],
        }

    def action_add_child(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dev.page',
            'view_mode': 'form',
            'context': {'default_parent_id': self.id, 'default_space_id': self.space_id.id},
        }


class DevPageVersion(models.Model):
    _name = 'dev.page.version'
    _description = 'Documentation Page Version'
    _order = 'date desc, id desc'

    page_id = fields.Many2one('dev.page', required=True, ondelete='cascade', index=True)
    name = fields.Char('Title')
    body = fields.Html(sanitize_style=True, readonly=True)
    author_id = fields.Many2one('res.users', 'Edited By', readonly=True)
    date = fields.Datetime('Edited On', readonly=True)

    @api.depends('page_id', 'date')
    def _compute_display_name(self):
        for version in self:
            version.display_name = '%s (%s)' % (
                version.name or version.page_id.name,
                version.date and fields.Datetime.context_timestamp(self, version.date).strftime('%d/%m/%Y %H:%M'))

    def action_restore(self):
        """Put this version back as the page's content (the current content is kept in the history)."""
        self.ensure_one()
        self.page_id.write({'body': self.body, 'name': self.name or self.page_id.name})
        self.page_id.message_post(body=_('Restored the version of %s.', self.display_name))
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.page', 'res_id': self.page_id.id,
                'view_mode': 'form'}

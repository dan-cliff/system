from odoo import _, api, fields, models
from odoo.exceptions import UserError


class VideoProductionProjectLink(models.TransientModel):
    """Create a new internal project for a video production, or link it to an
    existing internal project."""
    _name = 'video.production.project.link'
    _description = 'Video Production Project'

    production_id = fields.Many2one('video.production', required=True, ondelete='cascade')
    mode = fields.Selection(
        [('create', 'Create a New Internal Project'), ('link', 'Link an Existing Internal Project')],
        string='Project', required=True, default='create')
    project_id = fields.Many2one(
        'advanced.project', string='Internal Project',
        domain=[('is_internal', '=', True), ('is_template', '=', False)])
    name = fields.Char('Project Name', compute='_compute_name', store=True, readonly=False, precompute=True)
    template_id = fields.Many2one(
        'advanced.project', string='Start From Template', domain=[('is_template', '=', True)],
        help="Copy a template's phases and tasks. Leave empty to start from scratch.")
    date_start = fields.Date('Start Date', default=fields.Date.context_today)
    date_end = fields.Date('Target End Date', compute='_compute_name', store=True, readonly=False, precompute=True)

    @api.depends('production_id')
    def _compute_name(self):
        for wizard in self:
            wizard.name = wizard.production_id.name
            wizard.date_end = wizard.production_id.date_planned_publish

    def action_confirm(self):
        self.ensure_one()
        production = self.production_id
        if self.mode == 'link':
            if not self.project_id:
                raise UserError(_('Choose the internal project to link.'))
            project = self.project_id
        else:
            internal_type = self.env['advanced.project.type'].search([('is_internal', '=', True)], limit=1)
            if not internal_type:
                raise UserError(_('Add a Project Type marked Internal (Project › Configuration › Project Types) first.'))
            vals = {
                'name': self.name or production.name,
                'project_type_id': internal_type.id,
                'date_start': self.date_start,
                'date_end': self.date_end,
                'company_id': production.company_id.id,
                'description': production.description,
            }
            if self.template_id:
                project = self.template_id._create_from_template(vals)
                # the template's own type may be external: this project is internal
                project.project_type_id = internal_type
            else:
                project = self.env['advanced.project'].create(vals)
        production.project_id = project
        return project.action_open_project()

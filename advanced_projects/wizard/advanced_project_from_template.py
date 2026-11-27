from odoo import _, api, fields, models


class AdvancedProjectFromTemplate(models.TransientModel):
    """Start a project from a Project Template: its phases, tasks (with their
    links) and budget are copied, and every date moves with the new
    start date."""
    _name = 'advanced.project.from.template'
    _description = 'New Project from a Template'

    template_id = fields.Many2one(
        'advanced.project', string='Template', required=True, domain=[('is_template', '=', True)])
    name = fields.Char('Project Name', compute='_compute_name', store=True, readonly=False, required=True,
                       precompute=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    user_id = fields.Many2one(
        'res.users', string='Project Manager', default=lambda self: self.env.user, domain=[('share', '=', False)])
    date_start = fields.Date('Start Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    template_task_count = fields.Integer(related='template_id.task_count', string='Tasks in Template')

    @api.depends('template_id', 'partner_id')
    def _compute_name(self):
        for wizard in self:
            if wizard.template_id and wizard.partner_id:
                wizard.name = _('%(template)s – %(customer)s', template=wizard.template_id.name,
                                customer=wizard.partner_id.display_name)
            elif wizard.template_id:
                wizard.name = wizard.template_id.name

    def action_create(self):
        self.ensure_one()
        project = self.template_id._create_from_template({
            'name': self.name,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'date_start': self.date_start,
            'company_id': self.company_id.id,
        })
        return project.action_open_project()

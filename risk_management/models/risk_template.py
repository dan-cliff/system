from odoo import api, fields, models


class RiskTemplate(models.Model):
    _name = 'risk.template'
    _inherit = ['risk.ai.mixin', 'risk.activity.mixin']
    _description = 'Risk Assessment Template'
    _order = 'name'

    _ai_line_model = 'risk.template.line'
    _ai_line_parent_field = 'template_id'

    name = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    category_id = fields.Many2one('risk.category', string='Risk Category')
    line_ids = fields.One2many('risk.template.line', 'template_id', string='Risks', copy=True)
    risk_count = fields.Integer(compute='_compute_risk_count')

    @api.depends('line_ids')
    def _compute_risk_count(self):
        for template in self:
            template.risk_count = len(template.line_ids)

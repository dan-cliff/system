from odoo import fields, models


class RiskTemplateAction(models.Model):
    _name = 'risk.template.action'
    _description = 'Risk Template Standard Action'
    _order = 'sequence, id'

    template_line_id = fields.Many2one(
        'risk.template.line', string='Risk', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    description = fields.Text()

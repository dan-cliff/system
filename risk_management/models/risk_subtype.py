from odoo import fields, models


class RiskSubtype(models.Model):
    _name = 'risk.subtype'
    _description = 'Risk Subtype'
    _order = 'risk_type_id, name'

    name = fields.Char(required=True)
    risk_type_id = fields.Many2one(
        'risk.type', string='Risk Type', required=True, ondelete='cascade', index=True,
    )
    description = fields.Text()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (risk_type_id, name)',
        'A subtype with this name already exists for this risk type.',
    )

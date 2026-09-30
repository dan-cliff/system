from odoo import fields, models


class RiskType(models.Model):
    _name = 'risk.type'
    _description = 'Risk Type'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A risk type with this name already exists.',
    )

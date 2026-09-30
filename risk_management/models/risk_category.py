from odoo import fields, models


class RiskCategory(models.Model):
    _name = 'risk.category'
    _description = 'Risk Category'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A risk category with this name already exists.',
    )

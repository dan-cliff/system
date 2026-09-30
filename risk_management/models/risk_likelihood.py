from odoo import fields, models


class RiskLikelihood(models.Model):
    _name = 'risk.likelihood'
    _description = 'Risk Likelihood'
    _order = 'sequence, value'

    name = fields.Char(required=True)
    value = fields.Integer(
        required=True,
        help='Numeric weight used to calculate the risk score, e.g. 1 (Rare) to 5 (Almost Certain).',
    )
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _value_uniq = models.Constraint(
        'unique (value)',
        'A likelihood with this value already exists.',
    )

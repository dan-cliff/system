from odoo import fields, models


class RiskConsequence(models.Model):
    _name = 'risk.consequence'
    _description = 'Risk Consequence'
    _order = 'sequence, value'

    name = fields.Char(required=True)
    value = fields.Integer(
        required=True,
        help='Numeric weight used to calculate the risk score, e.g. 1 (Insignificant) to 5 (Catastrophic).',
    )
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _value_uniq = models.Constraint(
        'unique (value)',
        'A consequence with this value already exists.',
    )

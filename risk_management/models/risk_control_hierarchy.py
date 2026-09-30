from odoo import fields, models


class RiskControlHierarchy(models.Model):
    _name = 'risk.control.hierarchy'
    _description = 'Hierarchy of Controls'
    _order = 'sequence, id'

    name = fields.Char(string='Label', required=True)
    icon = fields.Image(string='Icon', max_width=128, max_height=128)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A hierarchy of controls level with this name already exists.',
    )

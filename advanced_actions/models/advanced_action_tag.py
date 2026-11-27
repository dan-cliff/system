from odoo import fields, models


class AdvancedActionTag(models.Model):
    _name = 'advanced.action.tag'
    _description = 'Action Tag'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', 'An Action Tag with this name already exists.')

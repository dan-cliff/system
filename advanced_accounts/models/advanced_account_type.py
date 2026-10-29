from odoo import fields, models


class AdvancedAccountType(models.Model):
    _name = 'advanced.account.type'
    _description = 'Account Type'
    _order = 'sequence, name, id'

    name = fields.Char('Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

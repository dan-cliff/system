from odoo import fields, models


class CustomDashboardWidgetCategory(models.Model):
    _name = 'custom.dashboard.widget.category'
    _description = 'Dashboard Widget Category'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    type_ids = fields.One2many(
        'custom.dashboard.widget.type', 'category_id', string='Widget Types',
    )

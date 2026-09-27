from odoo import fields, models


class ZooDiet(models.Model):
    _name = 'zoo.diet'
    _description = 'Diet'
    _order = 'name'

    name = fields.Char(required=True)
    species_id = fields.Many2one('zoo.species', help='Species this diet is intended for.')
    line_ids = fields.One2many('zoo.diet.line', 'diet_id', string='Food Items', copy=True)
    instructions = fields.Html()
    active = fields.Boolean(default=True)


class ZooDietLine(models.Model):
    _name = 'zoo.diet.line'
    _description = 'Diet Food Item'
    _order = 'diet_id, sequence, id'

    diet_id = fields.Many2one('zoo.diet', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    food = fields.Char(required=True)
    quantity = fields.Float(digits=(16, 3))
    unit = fields.Char(help='e.g. kg, g, pieces, scoops')
    frequency = fields.Selection(
        [
            ('twice_daily', 'Twice Daily'),
            ('daily', 'Daily'),
            ('alternate_days', 'Alternate Days'),
            ('weekly', 'Weekly'),
            ('as_needed', 'As Needed'),
        ],
        default='daily',
    )
    notes = fields.Char()

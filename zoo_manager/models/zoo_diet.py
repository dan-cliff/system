from odoo import api, fields, models


class ZooDiet(models.Model):
    _name = 'zoo.diet'
    _description = 'Diet'
    _order = 'name'

    name = fields.Char(required=True)
    class_id = fields.Many2one(
        'zoo.animal.class', string='Class', index=True,
        compute='_compute_class_id', store=True, readonly=False,
        help='Pick a class to narrow the species list.',
    )
    species_id = fields.Many2one(
        'zoo.species', help='Species this diet is intended for.',
        domain="[('class_id', '=', class_id)] if class_id else []",
    )
    line_ids = fields.One2many('zoo.diet.line', 'diet_id', string='Food Items', copy=True)
    instructions = fields.Html()
    active = fields.Boolean(default=True)

    @api.depends('species_id.class_id')
    def _compute_class_id(self):
        for diet in self:
            diet.class_id = diet.species_id.class_id or diet.class_id

    @api.onchange('class_id')
    def _onchange_class_id(self):
        if self.species_id and self.class_id and self.species_id.class_id != self.class_id:
            self.species_id = False


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

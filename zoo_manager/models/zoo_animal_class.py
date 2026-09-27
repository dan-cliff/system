from odoo import api, fields, models


class ZooAnimalClass(models.Model):
    _name = 'zoo.animal.class'
    _description = 'Animal Class'
    _inherit = ['zoo.prefix.code.mixin']
    _order = 'sequence, name'

    _prefix_code_length = 2

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    species_ids = fields.One2many('zoo.species', 'class_id', string='Species')
    species_count = fields.Integer(compute='_compute_species_count')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', 'A class with this name already exists.')
    _prefix_code_uniq = models.Constraint('UNIQUE (prefix_code)', 'Another class already uses this Prefix Code.')

    @api.depends('species_ids')
    def _compute_species_count(self):
        counts = dict(self.env['zoo.species']._read_group(
            [('class_id', 'in', self.ids)], ['class_id'], ['__count'],
        ))
        for animal_class in self:
            animal_class.species_count = counts.get(animal_class, 0)

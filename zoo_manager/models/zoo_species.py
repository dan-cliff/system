from odoo import api, fields, models


class ZooSpecies(models.Model):
    _name = 'zoo.species'
    _description = 'Species'
    _order = 'name'

    name = fields.Char(string='Common Name', required=True)
    scientific_name = fields.Char()
    animal_class = fields.Selection(
        [
            ('mammal', 'Mammal'),
            ('bird', 'Bird'),
            ('reptile', 'Reptile'),
            ('amphibian', 'Amphibian'),
            ('fish', 'Fish'),
            ('invertebrate', 'Invertebrate'),
        ],
        string='Class',
    )
    conservation_status = fields.Selection(
        [
            ('ne', 'Not Evaluated'),
            ('dd', 'Data Deficient'),
            ('lc', 'Least Concern'),
            ('nt', 'Near Threatened'),
            ('vu', 'Vulnerable'),
            ('en', 'Endangered'),
            ('cr', 'Critically Endangered'),
            ('ew', 'Extinct in the Wild'),
        ],
        string='Conservation Status (IUCN)',
    )
    default_diet_id = fields.Many2one(
        'zoo.diet',
        string='Default Diet',
        help='Diet given to new animals of this species.',
    )
    description = fields.Html()
    animal_ids = fields.One2many('zoo.animal', 'species_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', 'A species with this name already exists.')

    @api.depends('animal_ids')
    def _compute_animal_count(self):
        counts = dict(self.env['zoo.animal']._read_group(
            [('species_id', 'in', self.ids)], ['species_id'], ['__count'],
        ))
        for species in self:
            species.animal_count = counts.get(species, 0)

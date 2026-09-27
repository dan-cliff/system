from odoo import api, fields, models


class ZooSpecies(models.Model):
    _name = 'zoo.species'
    _description = 'Species'
    _inherit = ['zoo.prefix.code.mixin']
    _order = 'name'

    _prefix_code_length = 3

    name = fields.Char(string='Common Name', required=True)
    scientific_name = fields.Char()
    class_id = fields.Many2one('zoo.animal.class', string='Class', index=True)
    species_code = fields.Char(
        index=True,
        help='Regulatory species code used on the annual wildlife return.',
    )
    include_on_annual_return = fields.Boolean(
        string='Include on Annual Wildlife Return',
        help='Should this Species be included on the annual wildlife return?',
    )
    conservation_status_id = fields.Many2one('zoo.conservation.status', string='Conservation Status (IUCN)')
    default_diet_id = fields.Many2one(
        'zoo.diet',
        string='Default Diet',
        help='Diet given to new animals of this species.',
    )
    description = fields.Html()
    animal_ids = fields.One2many('zoo.animal', 'species_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count')
    active = fields.Boolean(default=True)

    # Common names are not unique: the wildlife schedule lists some twice (e.g.
    # subspecies), told apart by their Species Code.
    _species_code_uniq = models.Constraint('UNIQUE (species_code)', 'Another species already uses this Species Code.')
    _prefix_code_uniq = models.Constraint('UNIQUE (prefix_code)', 'Another species already uses this Prefix Code.')

    @api.depends('name', 'species_code')
    def _compute_display_name(self):
        for species in self:
            species.display_name = f'[{species.species_code}] {species.name}' if species.species_code else species.name

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ('ilike', '=') and isinstance(value, str) and value:
            return ['|', '|', '|',
                    ('name', operator, value), ('scientific_name', operator, value),
                    ('species_code', operator, value), ('prefix_code', operator, value)]
        return super()._search_display_name(operator, value)

    @api.depends('animal_ids')
    def _compute_animal_count(self):
        counts = dict(self.env['zoo.animal']._read_group(
            [('species_id', 'in', self.ids)], ['species_id'], ['__count'],
        ))
        for species in self:
            species.animal_count = counts.get(species, 0)

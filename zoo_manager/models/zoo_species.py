import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..lib import taxonomy_lookup

_logger = logging.getLogger(__name__)

# Scientific classification field for each taxonomic rank.
TAXON_FIELDS = {
    'kingdom': 'taxon_kingdom',
    'phylum': 'taxon_phylum',
    'class': 'taxon_class',
    'order': 'taxon_order',
    'family': 'taxon_family',
    'genus': 'taxon_genus',
    'species': 'taxon_species',
}
LOOKUP_FIELDS = list(TAXON_FIELDS.values()) + ['image', 'distribution_image']


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

    # Scientific classification
    taxon_kingdom = fields.Char(string='Kingdom')
    taxon_phylum = fields.Char(string='Phylum')
    taxon_class = fields.Char(string='Class', help='Taxonomic class, e.g. Mammalia.')
    taxon_order = fields.Char(string='Order')
    taxon_family = fields.Char(string='Family')
    taxon_genus = fields.Char(string='Genus')
    taxon_species = fields.Char(string='Species', help='Species name, e.g. Macropus giganteus.')
    image = fields.Image(max_width=1024, max_height=1024)
    image_128 = fields.Image(related='image', max_width=128, max_height=128, store=True)
    distribution_image = fields.Image(string='Geographic Distribution', max_width=1024, max_height=1024)
    reference_url = fields.Char(string='Reference', help='Wikipedia article the pictures were taken from.')
    lookup_pending = fields.Boolean(
        copy=False, index=True,
        help='Missing classification or pictures will be looked up from the scientific name.',
    )
    lookup_failures = fields.Integer(copy=False, help='Failed lookup attempts; retried up to 3 times.')
    animal_ids = fields.One2many('zoo.animal', 'species_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count')
    active = fields.Boolean(default=True)

    # Common names are not unique: the wildlife schedule lists some twice (e.g.
    # subspecies), told apart by their Species Code.
    _species_code_uniq = models.Constraint('UNIQUE (species_code)', 'Another species already uses this Species Code.')
    _prefix_code_uniq = models.Constraint('UNIQUE (prefix_code)', 'Another species already uses this Prefix Code.')

    def _missing_lookup_fields(self):
        self.ensure_one()
        return [name for name in LOOKUP_FIELDS if not self[name]]

    @api.model_create_multi
    def create(self, vals_list):
        species = super().create(vals_list)
        species.filtered(lambda s: s.scientific_name and s._missing_lookup_fields()).lookup_pending = True
        return species

    def write(self, vals):
        res = super().write(vals)
        if 'scientific_name' in vals:
            self.filtered(lambda s: s.scientific_name and s._missing_lookup_fields()).write(
                {'lookup_pending': True, 'lookup_failures': 0})
        return res

    def _lookup_classification(self):
        """Fill in empty classification fields and pictures from the scientific
        name. Only exact GBIF matches are used; filled-in values are never
        overwritten. Returns the fields that were filled."""
        self.ensure_one()
        vals = {}
        name = self.scientific_name
        missing_taxa = [rank for rank, field in TAXON_FIELDS.items() if not self[field]]
        if missing_taxa:
            found = taxonomy_lookup.lookup_classification(name)
            vals.update({TAXON_FIELDS[rank]: found[rank] for rank in missing_taxa if found.get(rank)})
        if not self.image or not self.distribution_image:
            pictures = taxonomy_lookup.lookup_images(name)
            if not self.image and pictures.get('image'):
                vals['image'] = pictures['image']
            if not self.distribution_image and pictures.get('distribution'):
                vals['distribution_image'] = pictures['distribution']
            if pictures.get('url') and not self.reference_url:
                vals['reference_url'] = pictures['url']
        vals.update(lookup_pending=False, lookup_failures=0)
        self.write(vals)
        return [field for field in vals if field in LOOKUP_FIELDS]

    def action_lookup_classification(self):
        filled = []
        for species in self.filtered('scientific_name'):
            try:
                filled += species._lookup_classification()
            except Exception as error:  # noqa: BLE001 - report network/parse errors to the user
                raise UserError(self.env._('Could not look up %(name)s: %(error)s',
                                           name=species.scientific_name, error=error)) from error
        message = (self.env._('Filled in: %s', ', '.join(self._fields[f].string for f in dict.fromkeys(filled)))
                   if filled else self.env._('Nothing new could be confirmed for this species.'))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': message, 'type': 'success' if filled else 'warning', 'sticky': False,
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    @api.model
    def _cron_lookup_classification(self, limit=25):
        """Scheduled action: look up species waiting for classification or
        pictures, a few at a time. A species that fails is retried on later
        runs, up to 3 times."""
        todo = self.search([('lookup_pending', '=', True), ('lookup_failures', '<', 3)], limit=limit)
        for species in todo:
            try:
                species._lookup_classification()
                self.env.cr.commit()
            except Exception:  # noqa: BLE001 - one failing species mustn't stop the rest
                self.env.cr.rollback()
                species.lookup_failures += 1
                self.env.cr.commit()
                _logger.warning('Species lookup failed for %s', species.scientific_name, exc_info=True)

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

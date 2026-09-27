from odoo import api, fields, models


class ZooFacility(models.Model):
    _name = 'zoo.facility'
    _description = 'Facility'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    description = fields.Html()
    location_ids = fields.One2many('zoo.location', 'facility_id', string='Locations')
    enclosure_ids = fields.One2many('zoo.enclosure', 'facility_id', string='Enclosures')
    location_count = fields.Integer(compute='_compute_counts')
    enclosure_count = fields.Integer(compute='_compute_counts')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE (code)', 'A facility with this code already exists.')

    @api.depends('location_ids', 'enclosure_ids')
    def _compute_counts(self):
        for facility in self:
            facility.location_count = len(facility.location_ids)
            facility.enclosure_count = len(facility.enclosure_ids)

    def action_view_locations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Locations'),
            'res_model': 'zoo.location',
            'view_mode': 'list,form',
            'domain': [('facility_id', '=', self.id)],
            'context': {'default_facility_id': self.id},
        }

    def action_view_enclosures(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Enclosures'),
            'res_model': 'zoo.enclosure',
            'view_mode': 'list,form',
            'domain': [('facility_id', '=', self.id)],
            'context': {'default_facility_id': self.id},
        }


class ZooLocation(models.Model):
    _name = 'zoo.location'
    _description = 'Location'
    _order = 'facility_id, sequence, name'

    name = fields.Char(required=True)
    facility_id = fields.Many2one('zoo.facility', required=True, index=True, ondelete='restrict')
    sequence = fields.Integer(default=10)
    description = fields.Html()
    enclosure_ids = fields.One2many('zoo.enclosure', 'location_id', string='Enclosures')
    enclosure_count = fields.Integer(compute='_compute_enclosure_count')
    active = fields.Boolean(default=True)

    _name_facility_uniq = models.Constraint(
        'UNIQUE (facility_id, name)', 'This facility already has a location with this name.')

    @api.depends('enclosure_ids')
    def _compute_enclosure_count(self):
        for location in self:
            location.enclosure_count = len(location.enclosure_ids)

    @api.depends('name', 'facility_id.name')
    @api.depends_context('show_facility')
    def _compute_display_name(self):
        for location in self:
            if location.facility_id and self.env.context.get('show_facility', True):
                location.display_name = f'{location.facility_id.name} / {location.name}'
            else:
                location.display_name = location.name

    def action_view_enclosures(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Enclosures'),
            'res_model': 'zoo.enclosure',
            'view_mode': 'list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id, 'default_facility_id': self.facility_id.id},
        }

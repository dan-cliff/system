# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .seek_api import SEEK_SCHEME

LOCATIONS_QUERY = """
query TalentSeekLocations($text: String!, $hirerId: String, $first: Int) {
  locationSuggestions(usageTypeCode: "PositionPosting", schemeId: "%s", hirerId: $hirerId, text: $text, first: $first) {
    location { id { value } name contextualName countryCode }
  }
}
""" % SEEK_SCHEME


class TalentSeekLocation(models.Model):
    _name = 'talent.seek.location'
    _description = 'SEEK Location'
    _order = 'name'

    name = fields.Char(string='Location', required=True)
    seek_id = fields.Char(string='SEEK ID', required=True, index=True)
    country_code = fields.Char(string='Country Code')
    active = fields.Boolean(default=True)

    _seek_id_uniq = models.Constraint('UNIQUE (seek_id)', 'This SEEK location is already listed.')

    @api.model
    def _seek_lookup(self, text, limit=10):
        company = self.env['talent.seek.api']._seek_company()
        data = self.env['talent.seek.api']._seek_query(
            LOCATIONS_QUERY, {'text': text, 'hirerId': company.seek_hirer_id, 'first': limit}, company)
        Locations = self.sudo().with_context(active_test=False)
        found = Locations.browse()
        for suggestion in data.get('locationSuggestions') or []:
            location = suggestion['location']
            vals = {'name': location.get('contextualName') or location['name'],
                    'country_code': location.get('countryCode'), 'active': True}
            existing = Locations.search([('seek_id', '=', location['id']['value'])], limit=1)
            if existing:
                existing.write(vals)
            else:
                existing = Locations.create(dict(vals, seek_id=location['id']['value']))
            found |= existing
        return found.sudo(False)

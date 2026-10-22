import logging
import time

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Nominatim (OpenStreetMap) allows one request a second.
OSM_DELAY_SECONDS = 1.1
# Towns geocoded per cron run, so a run stays short.
CRON_BATCH = 25
# Give up on a town after this many lookups found nothing.
MAX_ATTEMPTS = 3


def _city_key(city):
    return ' '.join((city or '').split()).lower()


class LiveCounterLocation(models.Model):
    """Town-level coordinates of buyers, shared by every counter.

    Only the town and country are geocoded (never a customer's street), and
    the result is cached here so each town is looked up once.
    """
    _name = 'live.counter.location'
    _description = 'Live Sales Counter Buyer Location'
    _order = 'country_id, city'

    name = fields.Char(compute='_compute_name', store=True)
    city = fields.Char(required=True)
    city_key = fields.Char(required=True, index=True)
    country_id = fields.Many2one('res.country', required=True, ondelete='cascade')
    latitude = fields.Float(digits=(10, 4))
    longitude = fields.Float(digits=(10, 4))
    # Technical geocoding state the cron depends on.
    state = fields.Selection(
        [('pending', 'Waiting'), ('done', 'Found'), ('failed', 'Not Found')],
        default='pending', required=True, index=True,
    )
    attempts = fields.Integer(readonly=True)
    date_geocoded = fields.Datetime(string='Last Lookup', readonly=True)

    _city_country_uniq = models.Constraint(
        'UNIQUE (city_key, country_id)', 'This town is already in the list for this country.')

    @api.depends('city', 'country_id')
    def _compute_name(self):
        for location in self:
            location.name = ', '.join(filter(None, [location.city, location.country_id.name]))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['city_key'] = _city_key(vals.get('city'))
        return super().create(vals_list)

    def write(self, vals):
        if 'city' in vals:
            vals['city_key'] = _city_key(vals['city'])
        if ('latitude' in vals or 'longitude' in vals) and 'state' not in vals:
            vals['state'] = 'done'
        return super().write(vals)

    def action_geocode(self):
        self.write({'state': 'pending', 'attempts': 0})
        self._geocode()

    # ── Lookups ────────────────────────────────────────────────────────────
    @api.model
    def _locate_partners(self, partners):
        """Return {partner_id: {'city', 'country', 'country_code', 'lat', 'lng'}}.

        lat / lng are None while the town waits to be geocoded; the page then
        places the buyer at the middle of their country. Coordinates are
        rounded to one decimal (about 10 km) so a public page never pinpoints
        a customer's home.
        """
        result = {}
        wanted = {}
        for partner in partners:
            country = partner.country_id
            loc = {
                'city': partner.city or '',
                'country': country.name or '',
                'country_code': country.code or '',
                'lat': None,
                'lng': None,
            }
            result[partner.id] = loc
            if 'partner_latitude' in partner._fields and (partner.partner_latitude or partner.partner_longitude):
                loc['lat'] = round(partner.partner_latitude, 1)
                loc['lng'] = round(partner.partner_longitude, 1)
            elif partner.city and country:
                wanted.setdefault((_city_key(partner.city), country.id), []).append((loc, partner.city))
        if not wanted:
            return result

        found = self.sudo().search([
            ('city_key', 'in', list({key for key, _country in wanted})),
            ('country_id', 'in', list({country for _key, country in wanted})),
        ])
        known = {(loc.city_key, loc.country_id.id): loc for loc in found}
        missing = []
        for key, entries in wanted.items():
            location = known.get(key)
            if location is None:
                missing.append({'city': entries[0][1].strip(), 'country_id': key[1]})
            elif location.state == 'done':
                for loc, _city in entries:
                    loc['lat'] = round(location.latitude, 1)
                    loc['lng'] = round(location.longitude, 1)
        if missing:
            self._queue(missing)
        return result

    @api.model
    def _queue(self, vals_list):
        """Add new towns for the cron to geocode (ignoring ones added meanwhile)."""
        created = False
        for vals in vals_list:
            try:
                with self.env.cr.savepoint():
                    self.sudo().create(vals)
                    created = True
            except IntegrityError:
                continue
        if created:
            self.env.ref('live_sales_counter.ir_cron_geocode_locations').sudo()._trigger()

    @api.model
    def _cron_geocode(self):
        self.search([('state', '=', 'pending')], order='attempts, id', limit=CRON_BATCH)._geocode()

    def _geocode(self):
        geocoder = self.env['base.geocoder']
        polite = geocoder._get_provider().tech_name == 'openstreetmap'
        for index, location in enumerate(self):
            if polite and index:
                time.sleep(OSM_DELAY_SECONDS)
            country = location.country_id.name
            try:
                query = geocoder.geo_query_address(city=location.city, country=country)
                coords = geocoder.geo_find(query, force_country=country)
            except UserError as error:
                _logger.info('Live Sales Counter: could not geocode %s: %s', location.name, error)
                coords = None
            vals = {'attempts': location.attempts + 1, 'date_geocoded': fields.Datetime.now()}
            if coords:
                vals.update(latitude=coords[0], longitude=coords[1], state='done')
            elif vals['attempts'] >= MAX_ATTEMPTS:
                vals['state'] = 'failed'
            else:
                vals['state'] = 'pending'
            location.write(vals)

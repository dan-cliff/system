# -*- coding: utf-8 -*-
import logging
from datetime import date

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Nager.Date: free, open-source public holiday API (no key), holidays per
# country with the ISO 3166-2 subdivisions (states) they apply to.
NAGER_URL = 'https://date.nager.at/api/v3/PublicHolidays/{year}/{country}'
NAGER_TIMEOUT = 20

# What a jurisdiction covers. Importing and matching employees' addresses
# depend on the country and state kinds, so this stays a fixed selection.
JURISDICTION_KINDS = [
    ('country', 'Country'),
    ('state', 'State / Region'),
    ('religion', 'Religion'),
    ('other', 'Other'),
]


class RosteringHolidayJurisdiction(models.Model):
    _name = 'rostering.holiday.jurisdiction'
    _description = 'Public Holiday Jurisdiction'
    _order = 'kind, country_id, name, id'

    name = fields.Char(string='Jurisdiction', required=True, translate=True)
    kind = fields.Selection(JURISDICTION_KINDS, string='Type', required=True, default='other')
    code = fields.Char(string='Code', index=True, help='e.g. AU for Australia, AU-NSW for New South Wales.')
    country_id = fields.Many2one('res.country', string='Country', index=True)
    state_id = fields.Many2one('res.country.state', string='State / Region', index=True,
                               domain="[('country_id', '=?', country_id)]")
    active = fields.Boolean(default=True)
    holiday_count = fields.Integer(string='Public Holidays', compute='_compute_holiday_count')

    def _compute_holiday_count(self):
        counts = dict(self.env['rostering.public.holiday']._read_group(
            [('jurisdiction_ids', 'in', self.ids)], ['jurisdiction_ids'], ['__count'],
        )) if self.ids else {}
        for jurisdiction in self:
            jurisdiction.holiday_count = counts.get(jurisdiction, 0)

    @api.onchange('state_id')
    def _onchange_state_id(self):
        if self.state_id:
            self.country_id = self.state_id.country_id

    @api.constrains('kind', 'country_id', 'state_id')
    def _check_kind(self):
        for jurisdiction in self:
            if jurisdiction.kind == 'country' and not jurisdiction.country_id:
                raise ValidationError(_('A Country jurisdiction needs its country.'))
            if jurisdiction.kind == 'state' and not jurisdiction.state_id:
                raise ValidationError(_('A State / Region jurisdiction needs its state.'))

    @api.model
    def _for_address(self, country, state):
        """The Country and State jurisdictions of an address."""
        jurisdictions = self.sudo().browse()
        if country:
            jurisdictions |= self.sudo().search([('kind', '=', 'country'), ('country_id', '=', country.id)])
        if state:
            jurisdictions |= self.sudo().search([('kind', '=', 'state'), ('state_id', '=', state.id)])
        return jurisdictions

    @api.model
    def _for_company(self, company):
        """Jurisdictions of a company's address: the default for its people."""
        return self._for_address(company.country_id, company.state_id)

    @api.model
    def _get_or_create(self, code):
        """The jurisdiction of an ISO 3166 code ("AU", "AU-NSW"), made if new."""
        jurisdiction = self.sudo().with_context(active_test=False).search([('code', '=', code)], limit=1)
        if jurisdiction:
            return jurisdiction
        country_code, _sep, state_code = code.partition('-')
        country = self.env['res.country'].search([('code', '=', country_code)], limit=1)
        if not state_code:
            return self.sudo().create({
                'name': country.name or code, 'kind': 'country', 'code': code, 'country_id': country.id,
            })
        state = self.env['res.country.state'].search([
            ('country_id', '=', country.id), ('code', '=', state_code),
        ], limit=1)
        if not state:
            # A subdivision Odoo does not list: keep it, as Other.
            return self.sudo().create({'name': code, 'kind': 'other', 'code': code, 'country_id': country.id})
        return self.sudo().create({
            'name': state.name, 'kind': 'state', 'code': code, 'country_id': country.id, 'state_id': state.id,
        })


class RosteringPublicHoliday(models.Model):
    _name = 'rostering.public.holiday'
    _description = 'Public Holiday'
    _order = 'date, name, id'

    name = fields.Char(string='Public Holiday', required=True, translate=True)
    local_name = fields.Char(string='Local Name')
    date = fields.Date(string='Date', required=True, index=True)
    jurisdiction_ids = fields.Many2many(
        'rostering.holiday.jurisdiction', 'rostering_public_holiday_jurisdiction_rel', 'holiday_id',
        'jurisdiction_id', string='Jurisdictions',
        help='Where the holiday applies (e.g. a country, a state or a religion). Leave empty for everyone.',
    )
    pay_multiplier = fields.Float(
        string='Pay Multiplier', digits=(16, 2), required=True,
        default=lambda self: self._default_pay_multiplier(),
        help='Penalty rate for work on this holiday: standard pay × this factor (e.g. 2.5).',
    )
    holiday_types = fields.Char(string='Holiday Types', help='Types given by the source, e.g. Public, Bank.')
    source = fields.Selection([('manual', 'Manual'), ('nager', 'Nager.Date')], string='Source',
                              default='manual', required=True, readonly=True)
    external_key = fields.Char(string='External Key', index=True, readonly=True, copy=False)
    note = fields.Text(string='Notes')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Leave empty to apply the holiday to every company.')

    @api.model
    def _default_pay_multiplier(self):
        try:
            return float(self.env['ir.config_parameter'].sudo().get_param(
                'advanced_rostering.holiday_pay_multiplier', 1.0))
        except ValueError:
            return 1.0

    @api.constrains('pay_multiplier')
    def _check_pay_multiplier(self):
        if any(holiday.pay_multiplier < 0 for holiday in self):
            raise ValidationError(_('The pay multiplier cannot be negative.'))

    @api.depends('name', 'date')
    def _compute_display_name(self):
        for holiday in self:
            holiday.display_name = '%s (%s)' % (holiday.name or '', holiday.date.strftime('%d/%m/%Y')) \
                if holiday.date else holiday.name

    # ------------------------------------------------------------------
    # Who a holiday applies to
    # ------------------------------------------------------------------
    @api.model
    def _in_range(self, date_from, date_to, companies=None):
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if companies is not None:
            domain += [('company_id', 'in', companies.ids + [False])]
        return self.sudo().search(domain)

    def _applying_to(self, jurisdictions, company=None):
        """The holidays of ``self`` that apply to someone in ``jurisdictions``:
        those without jurisdictions, or sharing one with them."""
        return self.filtered(lambda h: (not h.company_id or not company or h.company_id == company)
                             and (not h.jurisdiction_ids or h.jurisdiction_ids & jurisdictions))

    # ------------------------------------------------------------------
    # Import from Nager.Date
    # ------------------------------------------------------------------
    @api.model
    def _import_countries(self):
        companies = self.env['res.company'].sudo().search([])
        countries = companies.rostering_holiday_country_ids
        return countries or companies.country_id

    @api.model
    def _fetch_nager(self, year, country_code):
        response = requests.get(NAGER_URL.format(year=year, country=country_code), timeout=NAGER_TIMEOUT)
        if response.status_code in (204, 404):
            return []  # the country or year is not covered
        response.raise_for_status()
        return response.json() or []

    @api.model
    def _import_public_holidays(self, years=None, countries=None):
        """Create or update the public holidays of ``countries`` (by default
        those in Settings › Rostering, else the companies' countries) for
        ``years`` (by default this year and next). The pay multiplier,
        jurisdictions picked by hand and notes of existing holidays are kept.
        Returns the number of holidays created and updated."""
        today = fields.Date.context_today(self)
        years = years or [today.year, today.year + 1]
        countries = countries if countries is not None else self._import_countries()
        Jurisdiction = self.env['rostering.holiday.jurisdiction']
        created = updated = 0
        for country in countries.filtered('code'):
            for year in years:
                try:
                    items = self._fetch_nager(year, country.code)
                except (requests.RequestException, ValueError) as error:
                    raise UserError(_('Public holidays for %(country)s %(year)s could not be fetched from '
                                      'Nager.Date (date.nager.at): %(error)s',
                                      country=country.name, year=year, error=error)) from error
                for item in items:
                    types = item.get('types') or []
                    if 'Public' not in types:
                        continue  # bank, school, optional and observance days are not public holidays
                    # Nationwide, or only in the listed states ("AU-NSW").
                    codes = [] if item.get('global') else (item.get('counties') or [])
                    jurisdictions = Jurisdiction.browse()
                    for code in codes or [country.code]:
                        jurisdictions |= Jurisdiction._get_or_create(code)
                    key = 'nager:%s:%s:%s' % (country.code, item.get('date'), item.get('name'))
                    vals = {
                        'name': item.get('name') or item.get('localName'),
                        'local_name': item.get('localName'),
                        'date': date.fromisoformat(item['date']),
                        'holiday_types': ', '.join(types),
                    }
                    holiday = self.sudo().with_context(active_test=False).search(
                        [('external_key', '=', key)], limit=1)
                    if holiday:
                        holiday.write(dict(vals, jurisdiction_ids=[(4, j.id) for j in jurisdictions]))
                        updated += 1
                    else:
                        self.sudo().create(dict(vals, source='nager', external_key=key,
                                                jurisdiction_ids=[(6, 0, jurisdictions.ids)]))
                        created += 1
        self._after_import()
        return created, updated

    @api.model
    def _after_import(self):
        """Hook run after an import (Personnel links the new jurisdictions to employees)."""

    @api.model
    def _import_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('advanced_rostering.holiday_import') == 'True'

    @api.model
    def _cron_import_public_holidays(self):
        if not self._import_enabled():
            return
        try:
            created, updated = self._import_public_holidays()
            _logger.info('Rostering: imported public holidays (%s new, %s updated).', created, updated)
        except UserError as error:
            _logger.warning('Rostering: public holiday import failed: %s', error)

    @api.model
    def action_import_now(self):
        if not self.env.user.has_group('advanced_rostering.group_rostering_admin'):
            raise UserError(_('Only a Rostering Administrator can import public holidays.'))
        created, updated = self._import_public_holidays()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Public holidays imported'),
                'message': _('%(created)s new and %(updated)s updated public holidays from Nager.Date.',
                             created=created, updated=updated),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }


class ResCompany(models.Model):
    _inherit = 'res.company'

    rostering_holiday_country_ids = fields.Many2many(
        'res.country', 'res_company_rostering_holiday_country_rel', 'company_id', 'country_id',
        string='Public Holiday Countries',
        help='Countries whose public holidays Rostering imports. Empty: the company\'s country.',
    )

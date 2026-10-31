# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

NAGER_AU_2026 = [
    {'date': '2026-01-26', 'localName': 'Australia Day', 'name': 'Australia Day', 'countryCode': 'AU',
     'global': True, 'counties': None, 'types': ['Public']},
    {'date': '2026-03-09', 'localName': 'Labour Day', 'name': 'Labour Day', 'countryCode': 'AU',
     'global': False, 'counties': ['AU-VIC'], 'types': ['Public']},
    {'date': '2026-08-03', 'localName': 'Bank Holiday', 'name': 'Bank Holiday', 'countryCode': 'AU',
     'global': False, 'counties': ['AU-NSW'], 'types': ['Bank']},
]


@tagged('post_install', '-at_install')
class TestPublicHolidays(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.au = cls.env.ref('base.au')
        cls.vic = cls.env['res.country.state'].search([('country_id', '=', cls.au.id), ('code', '=', 'VIC')])
        cls.nsw = cls.env['res.country.state'].search([('country_id', '=', cls.au.id), ('code', '=', 'NSW')])
        cls.env.company.write({'country_id': cls.au.id, 'state_id': cls.nsw.id})
        cls.env['ir.config_parameter'].sudo().set_param('advanced_rostering.holiday_pay_multiplier', '2.5')
        cls.Holiday = cls.env['rostering.public.holiday']

    def _import(self):
        with patch.object(type(self.Holiday), '_fetch_nager',
                          lambda self, year, country: NAGER_AU_2026 if year == 2026 else []):
            return self.Holiday._import_public_holidays(years=[2026], countries=self.au)

    def test_import(self):
        self.assertEqual(self._import(), (2, 0))
        day = self.Holiday.search([('name', '=', 'Australia Day')])
        self.assertEqual(day.date, date(2026, 1, 26))
        self.assertEqual(day.jurisdiction_ids.kind, 'country')
        self.assertEqual(day.jurisdiction_ids.country_id, self.au)
        self.assertEqual(day.pay_multiplier, 2.5)
        labour = self.Holiday.search([('name', '=', 'Labour Day')])
        self.assertEqual(labour.jurisdiction_ids.state_id, self.vic)
        self.assertFalse(self.Holiday.search([('name', '=', 'Bank Holiday')]), 'only public holidays are imported')
        # Importing again updates; a pay multiplier set by hand is kept.
        day.pay_multiplier = 3.0
        self.assertEqual(self._import(), (0, 2))
        self.assertEqual(day.pay_multiplier, 3.0)

    def test_holidays_on_shifts(self):
        self._import()
        self.env['ir.config_parameter'].sudo().set_param('advanced_rostering.cycle', 'monthly')
        roster = self.env['rostering.roster'].create({'name': 'Shop', 'date_start': date(2026, 1, 10)})
        Shift = self.env['rostering.shift']
        holiday_shift = Shift.create({'roster_id': roster.id, 'date': date(2026, 1, 26), 'user_id': self.env.uid})
        normal_shift = Shift.create({'roster_id': roster.id, 'date': date(2026, 1, 27), 'user_id': self.env.uid})
        self.assertEqual(holiday_shift.public_holiday_name, 'Australia Day')
        self.assertEqual(holiday_shift.holiday_pay_multiplier, 2.5)
        self.assertFalse(normal_shift.public_holiday_name)
        self.assertEqual(roster.public_holiday_ids.mapped('name'), ['Australia Day'])
        # Victoria's Labour Day does not apply to a company in New South Wales.
        roster_march = self.env['rostering.roster'].create({'name': 'Shop', 'date_start': date(2026, 3, 1)})
        self.assertFalse(roster_march.public_holiday_ids)
        # A holiday without jurisdictions applies to everyone.
        self.Holiday.create({'name': 'Company Picnic', 'date': date(2026, 3, 20)})
        roster_march.invalidate_recordset(['public_holiday_ids'])
        self.assertEqual(roster_march.public_holiday_ids.mapped('name'), ['Company Picnic'])

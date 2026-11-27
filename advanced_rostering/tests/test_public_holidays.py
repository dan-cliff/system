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

    def test_leave_hours(self):
        from datetime import datetime
        from odoo.exceptions import ValidationError
        self.env['ir.config_parameter'].sudo().set_param('advanced_rostering.leave_hours_per_day', '7.6')
        self.env.user.tz = 'UTC'
        leave_type = self.env['rostering.leave.type'].create({'name': 'Annual'})
        Leave = self.env['rostering.leave']
        whole = Leave.create({'leave_type_id': leave_type.id, 'date_from': date(2026, 1, 19),
                              'date_to': date(2026, 1, 23)})
        self.assertEqual(whole.duration_days, 5)
        self.assertAlmostEqual(whole.hours, 38.0)
        self.assertFalse(whole.holiday_days)
        # Australia Day (26/01) is a public holiday for the company: not counted.
        self._import()
        over_holiday = Leave.create({'leave_type_id': leave_type.id, 'date_from': date(2026, 1, 26),
                                     'date_to': date(2026, 1, 28)})
        self.assertEqual(over_holiday.duration_days, 2)
        self.assertAlmostEqual(over_holiday.hours, 15.2)
        self.assertEqual(over_holiday.holiday_days, 1)
        self.assertAlmostEqual(over_holiday.holiday_hours, 7.6)
        # A part day: the hours between From and To, dated on that day.
        partial = Leave.create({'leave_type_id': leave_type.id, 'request_unit': 'partial',
                                'datetime_from': datetime(2026, 2, 2, 9, 0),
                                'datetime_to': datetime(2026, 2, 2, 12, 30)})
        self.assertEqual((partial.date_from, partial.date_to), (date(2026, 2, 2), date(2026, 2, 2)))
        self.assertAlmostEqual(partial.hours, 3.5)
        # Another part day the same afternoon is fine; an overlapping one is not.
        Leave.create({'leave_type_id': leave_type.id, 'request_unit': 'partial',
                      'datetime_from': datetime(2026, 2, 2, 13, 0), 'datetime_to': datetime(2026, 2, 2, 15, 0)})
        with self.assertRaises(ValidationError):
            Leave.create({'leave_type_id': leave_type.id, 'request_unit': 'partial',
                          'datetime_from': datetime(2026, 2, 2, 12, 0), 'datetime_to': datetime(2026, 2, 2, 14, 0)})
        # A part day stays on one day.
        with self.assertRaises(ValidationError):
            Leave.create({'leave_type_id': leave_type.id, 'request_unit': 'partial',
                          'datetime_from': datetime(2026, 2, 3, 9, 0), 'datetime_to': datetime(2026, 2, 4, 9, 0)})
        # A holiday added later is taken out of existing requests.
        self.Holiday.create({'name': 'Picnic Day', 'date': date(2026, 1, 21)})
        whole.invalidate_recordset(['hours', 'duration_days'])
        self.assertEqual(whole.duration_days, 4)
        self.assertAlmostEqual(whole.hours, 30.4)

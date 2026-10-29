from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAttendance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({'name': 'Sam Site', 'login': 'sam.onsite', 'tz': 'UTC'})
        cls.employee = cls.env['hr.employee'].create({'name': 'Sam Site', 'user_id': cls.user.id, 'tz': 'UTC'})
        # Flexible schedule: worked hours are the plain time between sign in and out.
        cls.employee.resource_calendar_id = cls.env['resource.calendar'].create({
            'name': 'Flexible', 'flexible_hours': True, 'tz': 'UTC',
        })
        cls.Attendance = cls.env['advanced.attendance']

    def test_worked_hours_and_name(self):
        attendance = self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 3, 2, 8, 0), 'check_out': datetime(2026, 3, 2, 16, 30),
        })
        self.assertAlmostEqual(attendance.worked_hours, 8.5)
        self.assertEqual(attendance.date, datetime(2026, 3, 2).date())
        self.assertEqual(attendance.company_id, self.employee.company_id)
        self.assertEqual(attendance.with_context(tz='UTC').display_name, 'Sam Site: 02/03/2026 08:00 - 16:30')

    def test_no_overlap_and_one_open(self):
        self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 3, 2, 8, 0), 'check_out': datetime(2026, 3, 2, 12, 0),
        })
        with self.assertRaises(ValidationError):
            self.Attendance.create({
                'employee_id': self.employee.id,
                'check_in': datetime(2026, 3, 2, 11, 0), 'check_out': datetime(2026, 3, 2, 13, 0),
            })
        with self.assertRaises(ValidationError):
            self.Attendance.create({
                'employee_id': self.employee.id,
                'check_in': datetime(2026, 3, 2, 7, 0), 'check_out': datetime(2026, 3, 2, 9, 0),
            })
        self.Attendance.create({'employee_id': self.employee.id, 'check_in': datetime(2026, 3, 3, 8, 0)})
        with self.assertRaises(ValidationError):
            self.Attendance.create({'employee_id': self.employee.id, 'check_in': datetime(2026, 3, 3, 9, 0)})
        with self.assertRaises(ValidationError):
            self.Attendance.create({
                'employee_id': self.employee.id,
                'check_in': datetime(2026, 3, 4, 9, 0), 'check_out': datetime(2026, 3, 4, 8, 0),
            })

    def test_cannot_duplicate(self):
        attendance = self.Attendance.create({'employee_id': self.employee.id, 'check_in': fields.Datetime.now()})
        with self.assertRaises(UserError):
            attendance.copy()

    def test_sign_in_out_from_odoo(self):
        employee = self.employee.with_user(self.user)
        data = employee._onsite_systray_data()
        self.assertEqual(data['state'], 'checked_out')
        attendance = employee._onsite_sign_in_out({'ip_address': '10.0.0.1', 'browser': 'firefox'})
        self.assertEqual(attendance.in_mode, 'systray')
        self.assertEqual(attendance.in_ip_address, '10.0.0.1')
        self.assertEqual(self.employee.onsite_state, 'checked_in')
        self.assertEqual(self.employee.hr_presence_state, 'present')
        employee._onsite_sign_in_out()
        self.assertTrue(attendance.check_out)
        self.assertEqual(attendance.out_mode, 'systray')
        self.assertEqual(self.employee.onsite_state, 'checked_out')

    def test_company_auto_sign_out(self):
        self.employee.company_id.write({'onsite_auto_sign_out': True, 'onsite_auto_sign_out_hours': 10})
        start = fields.Datetime.now() - timedelta(hours=11)
        attendance = self.Attendance.create({'employee_id': self.employee.id, 'check_in': start})
        self.Attendance._cron_auto_sign_out()
        self.assertEqual(attendance.out_mode, 'auto_check_out')
        self.assertEqual(attendance.check_out, start + timedelta(hours=10))

    def test_dates_show_day_first(self):
        self.assertEqual(self.env.ref('base.lang_en').date_format, '%d/%m/%Y')

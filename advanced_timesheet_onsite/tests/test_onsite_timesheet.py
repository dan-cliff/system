# -*- coding: utf-8 -*-
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.advanced_timesheet_onsite.hooks import post_init_hook, uninstall_hook


@tagged('post_install', '-at_install')
class TestOnsiteTimesheet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, onsite_no_alerts=True))
        cls.user = new_test_user(cls.env, 'ato_worker', groups='base.group_user', name='Sam Worker', tz='UTC')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Sam Worker', 'user_id': cls.user.id, 'tz': 'UTC',
            # Flexible hours: no lunch break is taken off the worked hours.
            'resource_calendar_id': False,
        })
        cls.env['ir.config_parameter'].sudo().set_param('advanced_timesheet.attendance_sync', 'True')
        cls.Attendance = cls.env['advanced.attendance']

    def _attend(self, start, end=None):
        return self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 10, 6, *start),
            'check_out': end and datetime(2026, 10, 6, *end),
        })

    def test_finished_attendance_fills_timesheet(self):
        attendance = self._attend((8, 0), (12, 30))
        line = attendance.advanced_timesheet_line_ids
        self.assertEqual(len(line), 1)
        self.assertTrue(line.is_auto)
        self.assertEqual(line.unit_amount, attendance.worked_hours)
        self.assertAlmostEqual(line.unit_amount, 4.5, places=2)
        self.assertEqual(line.date, attendance.date)
        self.assertEqual(line.sheet_id.employee_id, self.employee)
        self.assertEqual(line.name, 'Attendance 08:00 – 12:30')
        self.assertEqual(line._grid_row_labels()[0], 'Attendance')

    def test_open_attendance_has_no_entry_until_signed_out(self):
        attendance = self._attend((8, 0))
        self.assertFalse(attendance.advanced_timesheet_line_ids)
        attendance.check_out = datetime(2026, 10, 6, 10, 0)
        self.assertAlmostEqual(attendance.advanced_timesheet_line_ids.unit_amount, 2.0, places=2)

    def test_change_and_delete_follow_attendance(self):
        attendance = self._attend((8, 0), (12, 0))
        line = attendance.advanced_timesheet_line_ids
        attendance.check_out = datetime(2026, 10, 6, 15, 0)
        self.assertAlmostEqual(line.unit_amount, 7.0, places=2)
        attendance.check_in = datetime(2026, 10, 5, 22, 0)
        attendance.check_out = datetime(2026, 10, 5, 23, 0)
        self.assertEqual(line.date, attendance.date)
        self.assertEqual(attendance.advanced_timesheet_line_ids, line)
        attendance.check_out = False
        self.assertFalse(line.exists())
        attendance.check_out = datetime(2026, 10, 6, 1, 0)
        line = attendance.advanced_timesheet_line_ids
        self.assertTrue(line)
        attendance.unlink()
        self.assertFalse(line.exists())

    def test_hours_locked_but_details_editable(self):
        line = self._attend((8, 0), (12, 0)).advanced_timesheet_line_ids
        with self.assertRaises(UserError):
            line.unit_amount = 1.0
        line.name = 'Fencing'
        self.assertEqual(line.name, 'Fencing')

    def test_disabled_setting_and_catch_up(self):
        self.env['ir.config_parameter'].sudo().set_param('advanced_timesheet.attendance_sync', 'False')
        attendance = self._attend((8, 0), (9, 0))
        self.assertFalse(attendance.advanced_timesheet_line_ids)
        self.Attendance._cron_advanced_timesheet_sync()
        self.assertFalse(attendance.advanced_timesheet_line_ids)
        settings = self.env['res.config.settings'].create({'advanced_timesheet_attendance_sync': True})
        settings.execute()
        self.assertTrue(attendance.advanced_timesheet_line_ids)
        attendance.advanced_timesheet_line_ids.with_context(advanced_timesheet_sync=True).unlink()
        self.Attendance._cron_advanced_timesheet_sync()
        self.assertTrue(attendance.advanced_timesheet_line_ids)

    def test_hr_attendance_bridge_stands_down(self):
        if 'hr.attendance' not in self.env or 'attendance_id' not in self.env['advanced.timesheet.line']._fields:
            self.skipTest('advanced_timesheet_attendance is not installed')
        HrAttendance = self.env['hr.attendance']
        self.assertTrue(HrAttendance._advanced_timesheet_superseded())
        self.assertFalse(HrAttendance._advanced_timesheet_sync_enabled())
        old = HrAttendance.create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 10, 7, 8, 0), 'check_out': datetime(2026, 10, 7, 12, 0),
        })
        self.assertFalse(old.advanced_timesheet_line_ids)

    def test_takeover_and_hand_back(self):
        if 'hr.attendance' not in self.env or 'attendance_id' not in self.env['advanced.timesheet.line']._fields:
            self.skipTest('advanced_timesheet_attendance is not installed')
        times = {'check_in': datetime(2026, 10, 7, 8, 0), 'check_out': datetime(2026, 10, 7, 12, 0)}
        old = self.env['hr.attendance'].create(dict(times, employee_id=self.employee.id))
        # An entry made by advanced_timesheet_attendance before On Site took over.
        self.env['ir.config_parameter'].sudo().set_param('advanced_timesheet.attendance_sync', 'False')
        new = self._attend((0, 0), (1, 0))
        new.write(times)
        sheet = self.env['advanced.timesheet'].create({'employee_id': self.employee.id, 'date_start': '2026-10-07'})
        line = self.env['advanced.timesheet.line'].with_context(advanced_timesheet_sync=True).create({
            'sheet_id': sheet.id, 'date': '2026-10-07', 'unit_amount': 4.0, 'is_auto': True,
            'attendance_id': old.id, 'name': 'Kept description',
        })
        self.env['ir.config_parameter'].sudo().set_param('advanced_timesheet.attendance_sync', 'True')
        post_init_hook(self.env)
        self.assertEqual(line.onsite_attendance_id, new)
        self.assertFalse(line.attendance_id)
        self.assertEqual(line.name, 'Kept description')
        self.assertEqual(new.advanced_timesheet_line_ids, line)
        uninstall_hook(self.env)
        self.assertEqual(line.attendance_id, old)
        self.assertFalse(line.onsite_attendance_id)

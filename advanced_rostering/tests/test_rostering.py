# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.advanced_rostering.models.rostering_tools import period_bounds


@tagged('post_install', '-at_install')
class TestRostering(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('advanced_rostering.cycle', 'weekly')
        params.set_param('advanced_rostering.period_start', '2024-01-01')
        cls.planner = new_test_user(
            cls.env, 'ros_planner', name='Pat Planner', tz='UTC',
            groups='advanced_rostering.group_roster_edit_draft,advanced_rostering.group_roster_publish',
        )
        cls.worker = new_test_user(cls.env, 'ros_worker', name='Wes Worker', tz='UTC',
                                   groups='advanced_rostering.group_roster_own')
        cls.approver = new_test_user(cls.env, 'ros_approver', name='Ann Approver', tz='UTC',
                                     groups='advanced_rostering.group_leave_approve')
        cls.duty = cls.env['rostering.duty'].create({'name': 'Counter'})
        cls.standard = cls.env['rostering.standard.shift'].create({
            'name': 'Early', 'start_time': 6.0, 'end_time': 14.5, 'duty_id': cls.duty.id,
            'break_ids': [(0, 0, {'name': 'Lunch', 'start_time': 10.0, 'end_time': 10.5})],
        })
        cls.leave_type = cls.env['rostering.leave.type'].create({'name': 'Annual'})

    def _roster(self, day=date(2026, 11, 4)):
        return self.env['rostering.roster'].with_user(self.planner).create({'name': 'Shop', 'date_start': day})

    def test_period_bounds(self):
        self.assertEqual(period_bounds(self.env, date(2026, 11, 4), 'weekly'), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(period_bounds(self.env, date(2026, 11, 4), 'monthly'), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(period_bounds(self.env, date(2026, 11, 4), 'quarterly'), (date(2026, 10, 1), date(2026, 12, 31)))
        roster = self._roster()
        self.assertEqual((roster.date_start, roster.date_end), (date(2026, 11, 2), date(2026, 11, 8)))

    def test_shift_from_standard_shift(self):
        roster = self._roster()
        shift = self.env['rostering.shift'].with_user(self.planner).create({
            'roster_id': roster.id, 'user_id': self.worker.id, 'date': date(2026, 11, 3),
            'standard_shift_id': self.standard.id,
        })
        self.assertEqual((shift.start_time, shift.end_time), (6.0, 14.5))
        self.assertEqual(shift.duty_id, self.duty)
        self.assertEqual(len(shift.break_ids), 1)
        self.assertAlmostEqual(shift.paid_hours, 8.0)
        with self.assertRaises(ValidationError):
            shift.date = date(2026, 11, 20)

    def test_overnight_shift(self):
        roster = self._roster()
        shift = self.env['rostering.shift'].create({
            'roster_id': roster.id, 'user_id': self.worker.id, 'date': date(2026, 11, 3),
            'start_time': 22.0, 'end_time': 6.0,
        })
        self.assertAlmostEqual(shift.duration, 8.0)
        self.assertEqual(shift.end_datetime.date(), date(2026, 11, 4))

    def test_apply_template(self):
        template = self.env['rostering.template'].create({
            'name': 'Week',
            'line_ids': [
                (0, 0, {'week': 1, 'weekday': '0', 'user_id': self.worker.id, 'standard_shift_id': self.standard.id}),
                (0, 0, {'week': 1, 'weekday': '2', 'standard_shift_id': self.standard.id}),
            ],
        })
        roster = self._roster()
        roster.with_user(self.planner)._apply_template(template)
        self.assertEqual(len(roster.shift_ids), 2)
        self.assertEqual(sorted(roster.shift_ids.mapped('date')), [date(2026, 11, 2), date(2026, 11, 4)])
        self.assertEqual(roster.unassigned_count, 1)
        roster.with_user(self.planner)._apply_template(template, replace=True)
        self.assertEqual(len(roster.shift_ids), 2)

    def test_publish_and_visibility(self):
        roster = self._roster()
        self.env['rostering.shift'].with_user(self.planner).create({
            'roster_id': roster.id, 'user_id': self.worker.id, 'date': date(2026, 11, 3),
            'standard_shift_id': self.standard.id,
        })
        Shift = self.env['rostering.shift'].with_user(self.worker)
        self.assertFalse(Shift.search([]))
        roster.with_user(self.planner).action_publish()
        self.assertEqual(roster.state, 'published')
        self.assertEqual(len(Shift.search([])), 1)
        # Editing a published roster needs its own permission.
        with self.assertRaises(AccessError):
            roster.shift_ids.with_user(self.planner).write({'note': 'Changed'})
        # Unpublishing needs its own permission too.
        with self.assertRaises(AccessError):
            roster.with_user(self.planner).action_unpublish()
        with self.assertRaises(AccessError):
            roster.with_user(self.worker).action_publish()

    def test_my_roster(self):
        roster = self._roster(date.today())
        self.env['rostering.shift'].create({
            'roster_id': roster.id, 'user_id': self.worker.id, 'date': roster.date_start,
            'standard_shift_id': self.standard.id,
        })
        roster.action_publish()
        data = self.env['rostering.shift'].with_user(self.worker).get_my_roster()
        self.assertEqual(data['shift_count'], 1)
        self.assertTrue(data['can_request'])

    def test_leave_queue(self):
        leave = self.env['rostering.leave'].with_user(self.worker).create({
            'leave_type_id': self.leave_type.id, 'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 5),
        })
        self.assertEqual(leave.user_id, self.worker)
        self.assertEqual(leave.duration_days, 5)
        leave.with_user(self.worker).action_submit()
        self.assertEqual(leave.state, 'submitted')
        # Without Personnel there is no approver: the leave team approves.
        self.assertFalse(leave.approver_user_id)
        with self.assertRaises(AccessError):
            leave.with_user(self.worker).action_approve()
        to_approve = self.env['rostering.leave'].with_user(self.approver).search([('can_approve', '=', True)])
        self.assertIn(leave, to_approve)
        leave.with_user(self.approver).action_approve()
        self.assertEqual(leave.state, 'approved')
        with self.assertRaises(UserError):
            leave.with_user(self.worker).write({'date_to': date(2026, 12, 6)})

    def test_leave_for_others_and_overlap(self):
        with self.assertRaises(AccessError):
            self.env['rostering.leave'].with_user(self.worker).create({
                'user_id': self.approver.id, 'leave_type_id': self.leave_type.id,
                'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 1),
            })
        self.env['rostering.leave'].create({
            'user_id': self.worker.id, 'leave_type_id': self.leave_type.id,
            'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 3),
        })
        with self.assertRaises(ValidationError):
            self.env['rostering.leave'].create({
                'user_id': self.worker.id, 'leave_type_id': self.leave_type.id,
                'date_from': date(2026, 12, 3), 'date_to': date(2026, 12, 4),
            })

    def test_shift_on_leave(self):
        roster = self._roster()
        shift = self.env['rostering.shift'].create({
            'roster_id': roster.id, 'user_id': self.worker.id, 'date': date(2026, 11, 3),
            'standard_shift_id': self.standard.id,
        })
        self.assertFalse(shift.on_leave)
        leave = self.env['rostering.leave'].create({
            'user_id': self.worker.id, 'leave_type_id': self.leave_type.id,
            'date_from': date(2026, 11, 3), 'date_to': date(2026, 11, 3),
        })
        leave.action_submit()
        leave.action_approve()
        shift.invalidate_recordset(['on_leave', 'leave_id'])
        self.assertTrue(shift.on_leave)
        self.assertIn(shift, self.env['rostering.shift'].search([('on_leave', '=', True)]))

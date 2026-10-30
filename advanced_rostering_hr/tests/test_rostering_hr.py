# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRosteringHr(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        groups = ('advanced_rostering.group_roster_own,advanced_rostering.group_roster_team,'
                  'advanced_rostering.group_leave_edit_team')
        cls.boss_user = new_test_user(cls.env, 'rhr_boss', name='Bea Boss', groups=groups)
        cls.worker_user = new_test_user(cls.env, 'rhr_worker', name='Will Worker',
                                        groups='advanced_rostering.group_roster_own')
        cls.other_user = new_test_user(cls.env, 'rhr_other', name='Olly Other',
                                       groups='advanced_rostering.group_roster_own')
        Employee = cls.env['hr.employee']
        cls.boss = Employee.create({'name': 'Bea Boss', 'user_id': cls.boss_user.id})
        cls.worker = Employee.create({'name': 'Will Worker', 'user_id': cls.worker_user.id, 'parent_id': cls.boss.id})
        cls.no_login = Employee.create({'name': 'Nina No-Login', 'parent_id': cls.boss.id})
        cls.other = Employee.create({'name': 'Olly Other', 'user_id': cls.other_user.id})
        cls.leave_type = cls.env['rostering.leave.type'].create({'name': 'Annual'})

    def test_manager_approves(self):
        leave = self.env['rostering.leave'].with_user(self.worker_user).create({
            'leave_type_id': self.leave_type.id, 'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 2),
        })
        self.assertEqual(leave.employee_id, self.worker)
        self.assertEqual(leave.manager_id, self.boss)
        self.assertEqual(leave.approver_user_id, self.boss_user)
        leave.with_user(self.worker_user).action_submit()
        with self.assertRaises(AccessError):
            leave.with_user(self.other_user).action_approve()
        self.assertIn(leave, self.env['rostering.leave'].with_user(self.boss_user).search([('can_approve', '=', True)]))
        leave.with_user(self.boss_user).action_approve()
        self.assertEqual(leave.state, 'approved')

    def test_manager_requests_for_team(self):
        leave = self.env['rostering.leave'].with_user(self.boss_user).create({
            'employee_id': self.no_login.id, 'leave_type_id': self.leave_type.id,
            'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 1),
        })
        self.assertFalse(leave.user_id)
        with self.assertRaises(AccessError):
            self.env['rostering.leave'].with_user(self.boss_user).create({
                'employee_id': self.other.id, 'leave_type_id': self.leave_type.id,
                'date_from': date(2026, 12, 1), 'date_to': date(2026, 12, 1),
            })
        with self.assertRaises(AccessError):
            self.env['rostering.leave'].with_user(self.worker_user).create({
                'employee_id': self.no_login.id, 'leave_type_id': self.leave_type.id,
                'date_from': date(2026, 12, 2), 'date_to': date(2026, 12, 2),
            })

    def test_my_team_rosters(self):
        roster = self.env['rostering.roster'].create({'name': 'Shop', 'date_start': date(2026, 11, 4)})
        Shift = self.env['rostering.shift']
        for employee in (self.boss, self.worker, self.no_login, self.other):
            Shift.create({'roster_id': roster.id, 'employee_id': employee.id, 'date': date(2026, 11, 4)})
        roster.action_publish()
        team = Shift.with_user(self.boss_user).search([('in_my_team', '=', True)])
        self.assertEqual(team.employee_id, self.boss | self.worker | self.no_login)
        self.assertEqual(Shift.with_user(self.worker_user).search([]).employee_id, self.worker)
        self.assertEqual(self.env['rostering.shift'].with_user(self.boss_user)._my_manager_name(), False)
        self.assertEqual(self.env['rostering.shift'].with_user(self.worker_user)._my_manager_name(), 'Bea Boss')

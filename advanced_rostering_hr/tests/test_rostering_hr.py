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

    def test_employee_picker_lists_public_profiles(self):
        """A Personnel user whose Employees permissions cover nobody still
        finds everyone when picking a rostering employee."""
        self.worker_user.group_ids = [(4, self.env.ref('advanced_hr.group_personnel_user').id)]
        Employee = self.env['hr.employee'].with_user(self.worker_user)
        self.assertFalse(Employee.name_search('Olly'))
        picker = Employee.with_context(rostering_employee_picker=True)
        self.assertEqual([emp_id for emp_id, _name in picker.name_search('Olly')], [self.other.id])
        field_context = self.env['rostering.shift']._fields['employee_id'].context
        self.assertTrue(field_context.get('rostering_employee_picker'))

    def test_employee_holiday_jurisdictions(self):
        au = self.env.ref('base.au')
        vic = self.env['res.country.state'].search([('country_id', '=', au.id), ('code', '=', 'VIC')])
        Jurisdiction = self.env['rostering.holiday.jurisdiction']
        country = Jurisdiction.create({'name': 'Australia', 'kind': 'country', 'code': 'AU', 'country_id': au.id})
        state = Jurisdiction.create({'name': 'Victoria', 'kind': 'state', 'code': 'AU-VIC',
                                     'country_id': au.id, 'state_id': vic.id})
        religion = Jurisdiction.create({'name': 'Orthodox', 'kind': 'religion'})
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('advanced_rostering.holiday_import', 'True')
        params.set_param('advanced_rostering.employee_jurisdictions', 'True')
        self.worker.write({'private_country_id': au.id, 'private_state_id': vic.id})
        self.assertEqual(self.worker.rostering_holiday_jurisdiction_ids, country | state)
        # Picked by hand: kept when the address changes.
        self.worker.rostering_holiday_jurisdiction_ids |= religion
        self.worker.write({'private_state_id': False})
        self.assertEqual(self.worker.rostering_holiday_jurisdiction_ids, country | religion)

        holiday = self.env['rostering.public.holiday'].create({
            'name': 'Orthodox Easter', 'date': date(2026, 11, 4), 'jurisdiction_ids': [(6, 0, religion.ids)],
            'pay_multiplier': 2.0,
        })
        roster = self.env['rostering.roster'].create({'name': 'Shop', 'date_start': date(2026, 11, 4)})
        shifts = self.env['rostering.shift'].create([
            {'roster_id': roster.id, 'employee_id': self.worker.id, 'date': date(2026, 11, 4)},
            {'roster_id': roster.id, 'employee_id': self.other.id, 'date': date(2026, 11, 4)},
        ])
        self.assertEqual(shifts[0].public_holiday_ids, holiday)
        self.assertEqual(shifts[0].holiday_pay_multiplier, 2.0)
        self.assertFalse(shifts[1].public_holiday_ids)

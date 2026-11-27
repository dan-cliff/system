from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccess(TransactionCase):
    """The permissions of CLAUDE.md > Permissions on Attendances."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, *groups):
            return Users.create({
                'name': login.title(), 'login': login,
                'group_ids': [Command.link(cls.env.ref(f'advanced_attendance.{g}').id) for g in groups],
            })

        cls.nobody = user('nobody', 'group_onsite_user')
        cls.own = user('own', 'group_attendance_edit_own')
        cls.boss = user('boss', 'group_attendance_edit_team')
        cls.viewer = user('viewer', 'group_attendance_view_all')
        Employee = cls.env['hr.employee']
        cls.boss_emp = Employee.create({'name': 'Boss', 'user_id': cls.boss.id})
        cls.own_emp = Employee.create({'name': 'Own', 'user_id': cls.own.id, 'parent_id': cls.boss_emp.id})
        cls.other_emp = Employee.create({'name': 'Other'})
        Attendance = cls.env['advanced.attendance']
        now = fields.Datetime.now()
        cls.own_att = Attendance.create({'employee_id': cls.own_emp.id, 'check_in': now})
        cls.other_att = Attendance.create({'employee_id': cls.other_emp.id, 'check_in': now})

    def visible(self, user):
        return self.env['advanced.attendance'].with_user(user).search([])

    def test_without_permission_nothing(self):
        self.assertFalse(self.visible(self.nobody))

    def test_own(self):
        self.assertEqual(self.visible(self.own), self.own_att)
        self.own_att.with_user(self.own).write({'in_location': 'Gate'})
        with self.assertRaises(AccessError):
            self.own_att.with_user(self.own).unlink()

    def test_team(self):
        visible = self.visible(self.boss)
        self.assertIn(self.own_att, visible)
        self.assertNotIn(self.other_att, visible)

    def test_view_all(self):
        self.assertTrue({self.own_att, self.other_att} <= set(self.visible(self.viewer)))
        with self.assertRaises(AccessError):
            self.other_att.with_user(self.viewer).write({'in_location': 'Gate'})

    def test_administrator(self):
        admin_group = self.env.ref('advanced_attendance.group_onsite_admin')
        self.assertIn(self.env.ref('base.user_admin'), admin_group.user_ids)
        self.assertIn(self.env.ref('advanced_attendance.group_attendance_delete_all'), admin_group.all_implied_ids)


@tagged('post_install', '-at_install')
class TestOvertimeApproval(TransactionCase):
    """Approving extra hours is the "Attendances: Approve Extra Hours" permission."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.onsite_overtime_validation = 'by_manager'
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        view_all = cls.env.ref('advanced_attendance.group_attendance_view_all')
        approve = cls.env.ref('advanced_attendance.group_attendance_approve')
        cls.viewer = Users.create({'name': 'Viewer', 'login': 'ot.viewer', 'group_ids': [Command.link(view_all.id)]})
        cls.approver = Users.create({'name': 'Approver', 'login': 'ot.approver',
                                     'group_ids': [Command.link(view_all.id), Command.link(approve.id)]})
        calendar = cls.env['resource.calendar'].create({'name': 'Standard 8h', 'tz': 'UTC'})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Olive Overtime', 'tz': 'UTC', 'resource_calendar_id': calendar.id,
            'date_version': '2020-01-01', 'contract_date_start': '2020-01-01',
        })
        # A Monday, 08:00 - 19:00: 10 hours worked (less lunch), 2 extra.
        cls.attendance = cls.env['advanced.attendance'].create({
            'employee_id': cls.employee.id,
            'check_in': '2026-03-02 08:00:00', 'check_out': '2026-03-02 19:00:00',
        })

    def test_extra_hours_wait_for_approval(self):
        self.assertEqual(self.employee.onsite_ruleset_id, self.env.ref('advanced_attendance.onsite_default_ruleset'))
        self.assertAlmostEqual(self.attendance.overtime_hours, 2.0)
        self.assertEqual(self.attendance.overtime_status, 'to_approve')
        self.assertEqual(self.attendance.validated_overtime_hours, 0)

    def test_only_approvers_approve(self):
        with self.assertRaises(AccessError):
            self.attendance.with_user(self.viewer).action_approve_overtime()
        self.attendance.with_user(self.approver).action_approve_overtime()
        self.assertEqual(self.attendance.overtime_status, 'approved')
        self.assertAlmostEqual(self.attendance.validated_overtime_hours, 2.0)
        self.attendance.with_user(self.approver).action_refuse_overtime()
        self.assertEqual(self.attendance.overtime_status, 'refused')


@tagged('post_install', '-at_install')
class TestManualSignOut(TransactionCase):
    """The Sign Out button on the On Site Now board needs its own permission."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        view_all = cls.env.ref('advanced_attendance.group_attendance_view_all')
        manual = cls.env.ref('advanced_attendance.group_attendance_manual_sign_out')
        cls.viewer = Users.create({'name': 'Viewer', 'login': 'mso.viewer', 'group_ids': [Command.link(view_all.id)]})
        cls.warden = Users.create({'name': 'Warden', 'login': 'mso.warden',
                                   'group_ids': [Command.link(view_all.id), Command.link(manual.id)]})
        Employee = cls.env['hr.employee']
        cls.attendances = cls.env['advanced.attendance'].create([
            {'employee_id': Employee.create({'name': name}).id, 'check_in': fields.Datetime.now()}
            for name in ('Ana On Site', 'Ben On Site')
        ])

    def test_needs_permission(self):
        with self.assertRaises(AccessError):
            self.attendances.with_user(self.viewer).action_manual_sign_out()
        self.assertFalse(any(self.attendances.mapped('check_out')))

    def test_warden_signs_everyone_out(self):
        result = self.attendances.with_user(self.warden).action_manual_sign_out()
        self.assertTrue(all(self.attendances.mapped('check_out')))
        self.assertEqual(set(self.attendances.mapped('out_mode')), {'manual'})
        self.assertIn('Ana On Site', result['params']['message'])
        self.assertIn('Signed out manually by Warden', self.attendances[0].message_ids[0].body)

    def test_admin_has_it(self):
        admin_group = self.env.ref('advanced_attendance.group_onsite_admin')
        self.assertIn(self.env.ref('advanced_attendance.group_attendance_manual_sign_out'), admin_group.all_implied_ids)

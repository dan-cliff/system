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

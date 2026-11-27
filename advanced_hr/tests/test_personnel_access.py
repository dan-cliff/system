# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PersonnelCase


@tagged('post_install', '-at_install')
class TestPersonnelAccess(PersonnelCase):

    def test_own_sees_and_edits_only_own_in_personnel(self):
        Employee = self.personnel(self.user_own)
        self.assertEqual(Employee.search([]), self.emp_own)
        self.emp_own.with_user(self.user_own).with_context(personnel_app=True).write({'job_title': 'Keeper'})
        self.assertEqual(self.emp_own.job_title, 'Keeper')
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_own).write({'job_title': 'Nope'})
        # Version fields (department, job, ...) follow the employee.
        self.emp_own.with_user(self.user_own).write({'department_id': self.department.id})
        self.assertEqual(self.emp_own.department_id, self.department)
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_own).write({'department_id': self.department.id})

    def test_own_private_details_only(self):
        with self.assertRaises(AccessError):
            self.emp_own.with_user(self.user_own).unlink()
        self.emp_own.with_user(self.user_own).write({'private_email': 'olive@home.test'})
        self.assertEqual(self.emp_own.with_user(self.user_own).private_email, 'olive@home.test')
        self.env.invalidate_all()  # rules apply when reading from the database
        other = self.emp_other.with_user(self.user_own)
        self.assertEqual(other.name, 'Otto Other', 'Public profile stays readable')
        with self.assertRaises(AccessError):
            other.private_email  # noqa: B018
        self.assertEqual(other.get_formview_id(), self.env.ref('hr.hr_employee_public_view_form').id)

    def test_bank_accounts(self):
        Bank = self.env['res.partner.bank']
        own_bank = Bank.create({'acc_number': 'OWN-1', 'partner_id': self.emp_own.work_contact_id.id})
        other_bank = Bank.create({'acc_number': 'OTHER-1', 'partner_id': self.emp_other.work_contact_id.id})
        visible = Bank.with_user(self.user_own).search([('id', 'in', (own_bank | other_bank).ids)])
        self.assertEqual(visible, own_bank)
        visible = Bank.with_user(self.user_all).search([('id', 'in', (own_bank | other_bank).ids)])
        self.assertEqual(visible, own_bank | other_bank)

    def test_colleagues_public_details(self):
        """Other apps keep showing colleagues' public details."""
        self.env.invalidate_all()
        self.assertEqual(self.emp_report.with_user(self.user_own).parent_id.name, 'Tess Lead')
        self.assertEqual(self.emp_other.with_user(self.user_own).department_id, self.env['hr.department'])
        self.assertEqual(self.env['hr.employee'].with_user(self.user_own).search([]), self.emp_own)
        plain = self.env['hr.employee'].with_user(self.user_plain).search([('name', '=', 'Otto Other')])
        self.assertEqual(plain.name, 'Otto Other')
        with self.assertRaises(AccessError):
            plain.write({'job_title': 'Nope'})

    def test_team(self):
        Employee = self.personnel(self.user_team)
        self.assertEqual(Employee.search([]), self.emp_team_lead | self.emp_report)
        self.emp_report.with_user(self.user_team).write({'job_title': 'Senior Keeper'})
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_team).write({'job_title': 'Nope'})
        # Departments they manage, through their team.
        self.department.manager_id = self.emp_team_lead
        self.assertIn(self.department, self.personnel(self.user_team, 'hr.department').search([]))

    def test_create_only(self):
        Employee = self.personnel(self.user_create)
        employee = Employee.create({'name': 'New Starter'})
        self.assertEqual(Employee.search([]), employee)
        with self.assertRaises(AccessError):
            employee.write({'job_title': 'Changed'})

    def test_create_and_edit_own_created(self):
        employee = self.personnel(self.user_own).create({'name': 'Created By Own'})
        employee.write({'job_title': 'Gardener', 'department_id': self.department.id})
        self.assertEqual(employee.job_title, 'Gardener')

    def test_view_all_reads_private_but_cannot_write(self):
        Employee = self.personnel(self.user_view)
        found = Employee.search([('id', 'in', (self.emp_other | self.emp_report).ids)])
        self.assertEqual(len(found), 2)
        self.assertEqual(self.emp_other.with_user(self.user_view).private_email, 'otto@home.test')
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_view).write({'job_title': 'Nope'})

    def test_edit_all(self):
        self.emp_other.with_user(self.user_all).write({'private_email': 'new@home.test', 'job_title': 'Vet'})
        self.assertEqual(self.emp_other.private_email, 'new@home.test')
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_all).unlink()

    def test_delete_own(self):
        own = self.env['hr.employee'].search([('user_id', '=', self.user_delete_own.id)])
        created = self.personnel(self.user_delete_own).create({'name': 'Temp'})
        created.unlink()
        self.assertFalse(created.exists())
        with self.assertRaises(AccessError):
            self.emp_other.with_user(self.user_delete_own).unlink()
        self.assertTrue(own.exists())

    def test_multi_company(self):
        Employee = self.personnel(self.user_all)
        self.assertNotIn(self.emp_other_company, Employee.search([]))

    def test_departments(self):
        Department = self.personnel(self.user_own, 'hr.department')
        self.assertFalse(Department.search([]))
        with self.assertRaises(AccessError):
            self.department.with_user(self.user_own).write({'name': 'Renamed'})
        dep = self.personnel(self.user_all, 'hr.department').create({'name': 'Aviary'})
        dep.write({'name': 'Aviaries'})
        with self.assertRaises(AccessError):
            dep.unlink()
        # Everyone still reads department names elsewhere.
        self.assertEqual(self.department.with_user(self.user_own).name, 'Keepers')

    def test_administrator(self):
        admin = self.env.ref('base.user_admin')
        self.assertTrue(admin.has_group('advanced_hr.group_personnel_admin'))
        self.assertTrue(admin.has_group('advanced_hr.group_employee_delete_all'))
        self.assertTrue(admin.has_group('hr.group_hr_manager'))

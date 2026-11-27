# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestWorkingHours(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env['res.company']
        cls.group = Company.create({'name': 'Test Group'})
        cls.child = Company.create({'name': 'Test Crafts', 'parent_id': cls.group.id})
        cls.other = Company.create({'name': 'Test Unrelated'})
        Calendar = cls.env['resource.calendar']
        cls.group_hours = Calendar.create({'name': 'Group Hours', 'company_id': cls.group.id})
        cls.child_hours = Calendar.create({'name': 'Crafts Hours', 'company_id': cls.child.id})
        cls.other_hours = Calendar.create({'name': 'Unrelated Hours', 'company_id': cls.other.id})
        cls.shared_hours = Calendar.create({'name': 'Shared Hours', 'company_id': False})

    def _workcenter(self, company, calendar):
        return self.env['mrp.workcenter'].create({
            'name': 'Bench', 'company_id': company.id if company else False,
            'resource_calendar_id': calendar.id,
        })

    def test_parent_company_hours(self):
        workcenter = self._workcenter(self.child, self.group_hours)
        self.assertEqual(workcenter.resource_calendar_id, self.group_hours)
        self.assertEqual(workcenter.calendar_company_ids, self.group | self.child)
        # Its own company's and shared hours still work.
        workcenter.resource_calendar_id = self.child_hours
        workcenter.resource_calendar_id = self.shared_hours
        # The selector offers exactly these.
        domain = ['|', ('company_id', '=', False), ('company_id', 'in', workcenter.calendar_company_ids.ids)]
        offered = self.env['resource.calendar'].search(domain)
        self.assertIn(self.group_hours, offered)
        self.assertNotIn(self.other_hours, offered)

    def test_other_company_hours_refused(self):
        with self.assertRaises(ValidationError):
            self._workcenter(self.child, self.other_hours)
        # A parent can't use its child's hours.
        with self.assertRaises(ValidationError):
            self._workcenter(self.group, self.child_hours)
        workcenter = self._workcenter(self.child, self.group_hours)
        with self.assertRaises(ValidationError):
            workcenter.company_id = self.other


@tagged('post_install', '-at_install')
class TestRelatedCompanyWorkers(TransactionCase):

    def test_related_company_employees_sign_in(self):
        Company = self.env['res.company']
        group = Company.create({'name': 'Test Group Co'})
        crafts = Company.create({'name': 'Test Crafts Co', 'parent_id': group.id})
        sister = Company.create({'name': 'Test Sister Co', 'parent_id': group.id})
        unrelated = Company.create({'name': 'Test Other Co'})
        workcenter = self.env['mrp.workcenter'].create({
            'name': 'Kiln', 'company_id': crafts.id, 'resource_calendar_id': group.resource_calendar_id.id})
        Employee = self.env['hr.employee']
        own = Employee.create({'name': 'Own Worker', 'company_id': crafts.id, 'barcode': 'TREL-1'})
        from_group = Employee.create({'name': 'Group Worker', 'company_id': group.id, 'barcode': 'TREL-2'})
        from_sister = Employee.create({'name': 'Sister Worker', 'company_id': sister.id, 'barcode': 'TREL-3'})
        outsider = Employee.create({'name': 'Outside Worker', 'company_id': unrelated.id, 'barcode': 'TREL-4'})
        for employee in (own, from_group, from_sister):
            self.assertTrue(workcenter._terminal_can_use(employee), employee.name)
            self.assertEqual(workcenter._terminal_find_badge(employee.barcode), employee)
        self.assertFalse(workcenter._terminal_can_use(outsider))
        self.assertIsNone(workcenter._terminal_find_badge('TREL-4'))
        self.assertEqual(workcenter.terminal_company_ids, group | crafts | sister)
        names = [e['name'] for e in workcenter._terminal_data()['employees']]
        self.assertIn('Sister Worker', names)
        self.assertNotIn('Outside Worker', names)

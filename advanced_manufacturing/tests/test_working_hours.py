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

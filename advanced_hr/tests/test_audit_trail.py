# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import tagged

from .common import PersonnelCase


@tagged('post_install', '-at_install')
class TestAuditTrail(PersonnelCase):

    def entries(self, record):
        return self.env['advanced.hr.audit.trail'].search(
            [('res_model', '=', record._name), ('res_id', '=', record.id)], order='id')

    def test_one_entry_per_save_with_changed_fields_only(self):
        self.flush_audit()
        before = self.entries(self.emp_other)
        self.emp_other.with_user(self.user_all).write({
            'job_title': 'Head Keeper',
            'birthday': date(1990, 3, 4),
            'department_id': self.department.id,
            'work_phone': self.emp_other.work_phone,  # unchanged: not listed
        })
        self.emp_other.with_user(self.user_all).write({'job_title': 'Chief Keeper'})
        self.flush_audit()
        entry = self.entries(self.emp_other) - before
        self.assertEqual(len(entry), 1, 'One entry for the save (transaction)')
        self.assertEqual(entry.operation, 'write')
        self.assertEqual(entry.user_id, self.user_all)
        self.assertEqual(entry.employee_id, self.emp_other)
        lines = {line.field_name: line for line in entry.line_ids}
        self.assertEqual(set(lines), {'job_title', 'birthday', 'department_id'})
        self.assertEqual(lines['job_title'].old_value, '')
        self.assertEqual(lines['job_title'].new_value, 'Chief Keeper')
        self.assertEqual(lines['birthday'].new_value, '04/03/1990')
        self.assertEqual(lines['department_id'].new_value, self.department.display_name)

    def test_no_entry_when_nothing_changes(self):
        self.flush_audit()
        before = self.entries(self.emp_other)
        self.emp_other.write({'name': self.emp_other.name})
        self.flush_audit()
        self.assertEqual(self.entries(self.emp_other), before)

    def test_old_value_and_reverted_change(self):
        self.emp_other.job_title = 'Keeper'
        self.flush_audit()
        before = self.entries(self.emp_other)
        self.emp_other.write({'job_title': 'Vet', 'mobile_phone': '0400 000 000'})
        self.emp_other.write({'job_title': 'Keeper'})  # back to the original: not listed
        self.flush_audit()
        entry = self.entries(self.emp_other) - before
        self.assertEqual(entry.line_ids.mapped('field_name'), ['mobile_phone'])
        self.assertEqual(entry.line_ids.old_value, '')
        self.assertEqual(entry.line_ids.new_value, '0400 000 000')

    def test_create_and_delete(self):
        employee = self.env['hr.employee'].create({'name': 'Audit Me', 'job_title': 'Ranger'})
        self.flush_audit()
        created = self.entries(employee)
        self.assertEqual(created.operation, 'create')
        self.assertIn('job_title', created.line_ids.mapped('field_name'))
        employee_id = employee.id
        employee.unlink()
        deleted = self.env['advanced.hr.audit.trail'].search(
            [('res_model', '=', 'hr.employee'), ('res_id', '=', employee_id), ('operation', '=', 'unlink')])
        self.assertEqual(deleted.record_name, 'Audit Me')

    def test_departments_and_no_chatter_tracking(self):
        self.flush_audit()
        messages = self.department.message_ids
        self.department.write({'name': 'Big Cats'})
        self.flush_audit()
        entry = self.entries(self.department)[-1:]
        self.assertEqual(entry.line_ids.old_value, 'Keepers')
        self.assertEqual(entry.line_ids.new_value, 'Big Cats')
        self.assertEqual(self.department.message_ids, messages, 'No chatter tracking message')

    def test_access(self):
        self.emp_other.job_title = 'Visible'
        self.flush_audit()
        Audit = self.env['advanced.hr.audit.trail']
        self.assertTrue(Audit.with_user(self.user_audit).search([('res_id', '=', self.emp_other.id)]))
        self.assertFalse(Audit.with_user(self.user_own).has_access('read'))
        self.assertEqual(self.emp_other.with_user(self.user_audit).personnel_audit_count,
                         len(self.entries(self.emp_other)))

# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import PersonnelCase


@tagged('post_install', '-at_install')
class TestBadge(PersonnelCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Template = cls.env['advanced.hr.badge.template']
        cls.badge_all = Template.create({'name': 'Everyone'})
        cls.badge_other = Template.create({'name': 'Other Co', 'company_id': cls.other_company.id})
        cls.emp_other.barcode = '0451'

    def test_print_actions(self):
        for badge in (self.badge_all, self.badge_other):
            action = badge.report_action_id
            self.assertEqual(action.model, 'hr.employee')
            self.assertEqual(action.binding_model_id.model, 'hr.employee')
            self.assertEqual(action.paperformat_id.page_width, 54)
            self.assertEqual(action.paperformat_id.page_height, 86)
        self.assertFalse(self.badge_all.report_action_id.domain)
        self.assertEqual(self.badge_other.report_action_id.domain,
                         "[('company_id', '=', %d)]" % self.other_company.id)
        # The Print menu only offers the badges that suit the employee.
        Report = self.env['ir.actions.report']
        actions = (self.badge_all | self.badge_other).report_action_id
        self.assertEqual(Report.browse(actions.get_valid_action_reports('hr.employee', self.emp_other.ids)),
                         self.badge_all.report_action_id)
        self.assertEqual(Report.browse(actions.get_valid_action_reports('hr.employee', self.emp_other_company.ids)),
                         actions)
        # Odoo's fixed badge is no longer on the Print menu.
        self.assertFalse(self.env.ref('hr.hr_employee_print_badge').binding_model_id)

    def test_archive_and_delete(self):
        self.badge_all.active = False
        self.assertFalse(self.badge_all.report_action_id.binding_model_id)
        action = self.badge_other.report_action_id
        self.badge_other.unlink()
        self.assertFalse(action.exists())

    def test_render(self):
        self.badge_all.layout = [
            {'id': 'n', 'type': 'text', 'text': 'Hi {{ name }} ({{ department_id.name }})', 'x': 1, 'y': 1, 'w': 50, 'h': 8,
             'bold': True, 'color': 'company_primary'},
            {'id': 'q', 'type': 'qr', 'value': '{{ barcode }}', 'x': 1, 'y': 10, 'w': 15, 'h': 15},
            {'id': 'b', 'type': 'barcode', 'value': 'ID-{{ barcode }}', 'x': 1, 'y': 30, 'w': 40, 'h': 10},
            {'id': 's', 'type': 'shape', 'x': 0, 'y': 0, 'w': 5, 'h': 5, 'fill': '#FF5A6E", url(evil)'},
        ]
        self.emp_other.department_id = self.department
        html = self.env['ir.actions.report']._render_qweb_html(
            self.badge_all.report_action_id, self.emp_other.ids)[0].decode()
        self.assertIn('Hi Otto Other (Keepers)', html)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('font-weight:bold', html)
        self.assertNotIn('evil', html, 'Colours are validated')

    def test_badge_for_other_company_refused(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_html(self.badge_other.report_action_id, self.emp_other.ids)

    def test_private_fields_need_access(self):
        self.badge_all.layout = [{'id': 't', 'type': 'text', 'text': '[{{ private_email }}]', 'x': 0, 'y': 0, 'w': 50, 'h': 5}]
        rendered = self.badge_all._badge_render(self.emp_other.with_user(self.user_plain))
        self.assertEqual(rendered['elements'][0]['text'], '[]')
        rendered = self.badge_all._badge_render(self.emp_other)
        self.assertEqual(rendered['elements'][0]['text'], '[otto@home.test]')

    def test_designer_preview(self):
        Template = self.env['advanced.hr.badge.template']
        layout = [{'id': 'n', 'type': 'text', 'text': '{{ job_id.name }}'},
                  {'id': 'l', 'type': 'image', 'source': 'company_logo'}]
        labels = Template.badge_designer_preview(layout)
        Employee, Job = self.env['hr.employee'], self.env['hr.job']
        expected = '[%s › %s]' % (Employee._fields['job_id'].string, Job._fields['name'].string)
        self.assertEqual(labels['elements']['n']['text'], expected)
        self.assertTrue(labels['colors']['company_primary'].startswith('#'))
        values = Template.badge_designer_preview(layout, self.emp_other.id)
        self.assertEqual(values['elements']['n']['text'], '')
        self.assertTrue(values['elements']['l']['src'].startswith('data:image/'))

    def test_print_badge_button(self):
        action = self.emp_other.action_print_personnel_badge()
        self.assertEqual(action['report_name'], 'advanced_hr.report_badge')

    def test_settings_without_personnel_rights(self):
        """Settings opens for administrators who have no Personnel permission."""
        from odoo.addons.mail.tests.common import mail_new_test_user
        admin = mail_new_test_user(self.env, login='settings_only', groups='base.group_user,base.group_system,hr.group_hr_manager')
        self.assertFalse(admin.has_group('advanced_hr.group_personnel_user'))
        Settings = self.env['res.config.settings'].with_user(admin)
        settings = Settings.create({})
        self.assertEqual(settings.personnel_badge_count, self.env['advanced.hr.badge.template'].search_count([]))
        arch = Settings.get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('name="hr"', arch, 'The Personnel settings still show')
        self.assertNotIn('personnel_badge_count', arch, 'ID Badges are for Personnel Administrators')

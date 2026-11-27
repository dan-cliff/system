# -*- coding: utf-8 -*-
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests.common import TransactionCase


class PersonnelCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=False))
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].create({'name': 'Other Company'})

        def user(login, groups):
            return mail_new_test_user(cls.env, login=login, groups='base.group_user,' + groups,
                                      company_id=cls.company.id, company_ids=[(6, 0, cls.company.ids)])

        cls.user_own = user('p_own', 'advanced_hr.group_employee_edit_own')
        cls.user_team = user('p_team', 'advanced_hr.group_employee_edit_team,advanced_hr.group_department_edit_team')
        cls.user_create = user('p_create', 'advanced_hr.group_employee_create_only')
        cls.user_view = user('p_view', 'advanced_hr.group_employee_view_all,advanced_hr.group_department_view_all')
        cls.user_all = user('p_all', 'advanced_hr.group_employee_edit_all,advanced_hr.group_department_edit_all')
        cls.user_delete_own = user('p_del_own', 'advanced_hr.group_employee_edit_own,advanced_hr.group_employee_delete_own')
        cls.user_audit = user('p_audit', 'advanced_hr.group_audit_trail_view')
        cls.user_plain = user('p_plain', 'base.group_user')

        Employee = cls.env['hr.employee']
        cls.department = cls.env['hr.department'].create({'name': 'Keepers'})
        cls.emp_team_lead = Employee.create({'name': 'Tess Lead', 'user_id': cls.user_team.id,
                                             'department_id': cls.department.id})
        cls.emp_report = Employee.create({'name': 'Rory Report', 'parent_id': cls.emp_team_lead.id,
                                          'department_id': cls.department.id, 'private_email': 'rory@home.test'})
        cls.emp_own = Employee.create({'name': 'Olive Own', 'user_id': cls.user_own.id})
        cls.emp_other = Employee.create({'name': 'Otto Other', 'private_email': 'otto@home.test'})
        cls.emp_other_company = Employee.create({'name': 'Cora Elsewhere', 'company_id': cls.other_company.id})
        cls.env['hr.employee'].create({'name': 'Dee Delete', 'user_id': cls.user_delete_own.id})

    def personnel(self, user, model='hr.employee'):
        """The model as the user sees it in Personnel."""
        return self.env[model].with_user(user).with_context(personnel_app=True)

    def flush_audit(self):
        self.env.flush_all()
        self.env.cr.precommit.run()

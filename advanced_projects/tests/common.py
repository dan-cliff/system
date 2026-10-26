from datetime import date

from odoo.tests import TransactionCase, new_test_user

PREFIX = 'advanced_projects.group_advanced_project_'


class AdvancedProjectCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.admin = new_test_user(cls.env, 'ap_admin', groups=PREFIX + 'manager', email='admin@example.com')
        cls.stage_todo = cls.env.ref('advanced_projects.task_stage_todo')
        cls.stage_blocked = cls.env.ref('advanced_projects.task_stage_blocked')
        cls.stage_done = cls.env.ref('advanced_projects.task_stage_done')
        cls.customer_company = cls.env['res.partner'].create({'name': 'Acme Farms', 'is_company': True})
        cls.customer = cls.env['res.partner'].create({
            'name': 'Jo Bloggs', 'email': 'jo@acme.example', 'parent_id': cls.customer_company.id,
        })

    @classmethod
    def _user(cls, login, *perms, **kwargs):
        groups = ','.join(PREFIX + p for p in perms) or PREFIX + 'user'
        return new_test_user(cls.env, login, groups=groups, email=f'{login}@example.com', **kwargs)

    def _project(self, user=None, **vals):
        Project = self.env['advanced.project']
        if user:
            Project = Project.with_user(user)
        return Project.create(dict({'name': 'Website Launch', 'date_start': date(2026, 3, 2)}, **vals))

    def _task(self, project, **vals):
        return self.env['advanced.project.task'].create(dict({'name': 'Task', 'project_id': project.id}, **vals))

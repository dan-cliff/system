from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

P = 'advanced_projects.group_advanced_project_'


@tagged('post_install', '-at_install')
class TestAdvancedActionsProject(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.employee = new_test_user(cls.env, 'aap_employee', groups=P + 'edit_own')
        cls.other = new_test_user(cls.env, 'aap_other', groups=P + 'edit_own')
        cls.assignee = new_test_user(cls.env, 'aap_assignee', groups=P + 'task_edit_own')
        cls.project = cls.env['advanced.project'].with_user(cls.employee).create({'name': 'Barn Build'})
        cls.task = cls.env['advanced.project.task'].create({
            'name': 'Order timber', 'project_id': cls.project.id, 'user_ids': [(6, 0, cls.assignee.ids)]})

    def test_employee_raises_actions_on_their_project(self):
        action = self.project.with_user(self.employee).action_open_actions()
        Action = self.env['advanced.action'].with_user(self.employee).with_context(action['context'])
        follow_up = Action.create({'name': 'Book the crane'})
        self.assertEqual(follow_up.source_app, 'project')
        self.assertEqual(follow_up.project_id, self.project)
        self.assertEqual(follow_up.company_id, self.project.company_id)
        self.assertEqual(self.project.with_user(self.employee).action_count, 1)
        follow_up.with_user(self.employee).write({'name': 'Book the big crane'})
        # people without access to the project see none of its actions
        with self.assertRaises(AccessError):
            follow_up.with_user(self.other).read(['name'])

    def test_task_actions_follow_task_permissions(self):
        follow_up = self.env['advanced.action'].with_user(self.assignee).create({
            'name': 'Get three quotes', 'project_task_id': self.task.id, 'user_ids': [(6, 0, self.assignee.ids)]})
        self.assertEqual(follow_up.project_id, self.project)
        self.assertEqual(self.task.with_user(self.assignee).action_count, 1)
        self.assertEqual(follow_up._action_source()[1], self.task)

    def test_portal_users_cannot_raise_project_actions(self):
        customer = new_test_user(self.env, 'aap_customer', groups='advanced_projects.group_advanced_project_customer')
        with self.assertRaises(AccessError):
            self.env['advanced.action'].with_user(customer).create({'name': 'Hack', 'project_id': self.project.id})
        with self.assertRaises(AccessError):
            self.env['advanced.action'].with_user(customer).search([])

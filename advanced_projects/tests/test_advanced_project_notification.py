from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import AdvancedProjectCommon


@tagged('post_install', '-at_install')
class TestAdvancedProjectNotification(AdvancedProjectCommon):
    """Project Types and the Notification Templates (used while Workflow
    Automation is not installed)."""

    def _mails(self, record):
        return self.env['mail.mail'].sudo().search([('model', '=', record._name), ('res_id', '=', record.id)])

    def test_project_types(self):
        internal = self.env.ref('advanced_projects.project_type_internal')
        project = self._project()
        self.assertFalse(project.is_internal)
        self.assertEqual(project.project_type_id, self.env.ref('advanced_projects.project_type_external'))
        project.project_type_id = internal
        self.assertTrue(project.is_internal)
        default_internal = self.env['advanced.project'].with_context(default_is_internal=True).create({'name': 'Ops'})
        self.assertEqual(default_internal.project_type_id, internal)
        template = self.env.ref('advanced_projects.template_customer_onboarding')
        template.project_type_id = internal
        from_template = template._create_from_template({'name': 'Internal onboarding'})
        self.assertEqual(from_template.project_type_id, internal)

    def test_task_assigned_and_overdue(self):
        worker = self._user('ap_notified', 'edit_own')
        project = self._project()
        task = self._task(project, user_ids=[(6, 0, worker.ids)])
        mails = self._mails(task)
        self.assertEqual(len(mails), 1)
        self.assertIn(worker.partner_id, mails.recipient_ids)
        self.assertIn('Task assigned to you', mails.subject)
        # overdue: once, from the daily run
        task.date_end = fields.Date.today() - timedelta(days=1)
        Notification = self.env['advanced.project.notification']
        Notification._cron_notify_deadlines()
        Notification._cron_notify_deadlines()
        self.assertEqual(len(self._mails(task).filtered(lambda m: 'Overdue' in m.subject)), 1)

    def test_project_events_reach_customers_only_when_shared(self):
        user = self.env['res.users'].create({
            'name': 'Cust', 'login': 'ap_notif_cust', 'email': 'cust@example.com',
            'group_ids': [(6, 0, self.env.ref('advanced_projects.group_advanced_project_customer').ids)],
        })
        project = self._project(self.admin)
        self.env['advanced.project.collaborator'].create({
            'project_id': project.id, 'partner_id': user.partner_id.id, 'collaborator_type': 'customer'})
        template = self.env['advanced.project.notification'].create({
            'name': 'Stage changed', 'event': 'project_stage', 'notify_customers': True, 'notify_team': True,
            'subject': 'Moved', 'body_html': '<p>Moved</p>',
        })
        project.stage_id = self.env.ref('advanced_projects.project_stage_in_progress')
        self.assertIn(user.partner_id, self._mails(project).recipient_ids)
        # internal projects never email customers
        project.project_type_id = self.env.ref('advanced_projects.project_type_internal')
        self._mails(project).unlink()
        project.stage_id = self.env.ref('advanced_projects.project_stage_on_hold')
        self.assertNotIn(user.partner_id, self._mails(project).recipient_ids)
        self.assertTrue(template)

    def test_workflow_automation_takes_over(self):
        module = self.env['ir.module.module'].sudo().search([('name', '=', 'workflow_automation')])
        if not module:
            module = self.env['ir.module.module'].sudo().create({'name': 'workflow_automation', 'state': 'uninstalled'})
        menu = self.env.ref('advanced_projects.menu_advanced_projects_notification')
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.admin)._visible_menu_ids())
        module.state = 'installed'
        self.env['ir.ui.menu'].env.registry.clear_cache()
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.admin)._visible_menu_ids())
        worker = self._user('ap_not_notified', 'edit_own')
        task = self._task(self._project(), user_ids=[(6, 0, worker.ids)])
        self.assertFalse(self._mails(task))

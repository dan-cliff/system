from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.addons.mail.tools.discuss import Store

from .common import AdvancedProjectCommon


@tagged('post_install', '-at_install')
class TestAdvancedProjectAccess(AdvancedProjectCommon):
    """The per-permission access model (CLAUDE.md > Permissions), the Project
    Customer permission set and Private comments."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nobody = cls._user('ap_nobody')
        cls.creator = cls._user('ap_creator', 'create_only')
        cls.own = cls._user('ap_own', 'edit_own')
        cls.lead = cls._user('ap_lead', 'edit_team')
        cls.member = cls._user('ap_member', 'edit_own')
        cls.viewer = cls._user('ap_viewer', 'view_all')
        cls.deleter = cls._user('ap_deleter', 'edit_own', 'delete_own')
        lead_employee = cls.env['hr.employee'].create({'name': 'Lead', 'user_id': cls.lead.id})
        cls.env['hr.employee'].create({'name': 'Member', 'user_id': cls.member.id, 'parent_id': lead_employee.id})

    def test_no_permission_no_access(self):
        project = self._project()
        with self.assertRaises(AccessError):
            project.with_user(self.nobody).read(['name'])
        with self.assertRaises(AccessError):
            self._project(self.nobody)

    def test_create_only(self):
        project = self._project(self.creator)
        task = self._task(project)
        self.assertEqual(project.with_user(self.creator).name, 'Website Launch')
        self.assertEqual(task.with_user(self.creator).name, 'Task')
        with self.assertRaises(AccessError):
            project.with_user(self.creator).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            self._project(user_id=False).with_user(self.creator).read(['name'])

    def test_edit_own_covers_managed_and_team_projects(self):
        created = self._project(self.own)
        managed = self._project(user_id=self.own.id)
        on_team = self._project(user_id=False)
        self.env['advanced.project.collaborator'].create({
            'project_id': on_team.id, 'partner_id': self.own.partner_id.id, 'collaborator_type': 'colleague',
        })
        other = self._project(user_id=False)
        Project = self.env['advanced.project'].with_user(self.own)
        projects = created | managed | on_team | other
        self.assertEqual(Project.search([('id', 'in', projects.ids)]), created | managed | on_team)
        # children follow their project
        task = self._task(on_team)
        task.with_user(self.own).write({'name': 'Renamed'})
        with self.assertRaises(AccessError):
            self._task(other).with_user(self.own).read(['name'])
        with self.assertRaises(AccessError):
            created.with_user(self.own).unlink()

    def test_edit_my_team(self):
        team_project = self._project(self.member)
        other = self._project(user_id=False)
        Project = self.env['advanced.project'].with_user(self.lead)
        self.assertEqual(Project.search([('id', 'in', (team_project | other).ids)]), team_project)
        team_project.with_user(self.lead).write({'name': 'Lead edit'})

    def test_view_all(self):
        project = self._project(user_id=False)
        task = self._task(project)
        self.assertEqual(task.with_user(self.viewer).name, 'Task')
        with self.assertRaises(AccessError):
            project.with_user(self.viewer).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            task.with_user(self.viewer).write({'name': 'Changed'})

    def test_delete_own(self):
        mine = self._project(self.deleter)
        other = self._project(user_id=False)
        mine.with_user(self.deleter).unlink()
        with self.assertRaises(AccessError):
            other.with_user(self.deleter).unlink()

    def test_templates_readable_by_every_user(self):
        template = self.env.ref('advanced_projects.template_customer_onboarding')
        self.assertEqual(template.with_user(self.creator).name, 'Customer Onboarding')
        self.assertTrue(template.with_user(self.creator).task_ids)
        with self.assertRaises(AccessError):
            template.with_user(self.creator).write({'name': 'Changed'})

    def test_save_as_template_needs_administrator(self):
        project = self._project(self.own)
        with self.assertRaises(AccessError):
            project.with_user(self.own).action_save_as_template()
        project.with_user(self.admin).action_save_as_template()
        self.assertTrue(self.env['advanced.project'].search([('is_template', '=', True),
                                                             ('name', '=', 'Website Launch (Template)')]))

    # ------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------

    def _portal_customer(self, login, partner, with_group=True):
        groups = 'advanced_projects.group_advanced_project_customer' if with_group else 'base.group_portal'
        return new_test_user(self.env, login, groups=groups, partner_id=partner.id)

    def test_customer_sees_only_their_projects(self):
        user = self._portal_customer('ap_customer', self.customer)
        mine = self._project(user_id=False)
        self.env['advanced.project.collaborator'].create({
            'project_id': mine.id, 'partner_id': self.customer.id, 'collaborator_type': 'customer',
        })
        other = self._project(user_id=False)
        shared = self._task(mine, name='Shared')
        hidden = self._task(mine, name='Internal', customer_visible=False)
        draft = self.env['advanced.project.update'].create({'project_id': mine.id})
        published = self.env['advanced.project.update'].create({'project_id': mine.id, 'name': 'Week 1'})
        published.with_user(self.admin).action_publish()

        Project = self.env['advanced.project'].with_user(user)
        self.assertEqual(Project.search([('id', 'in', (mine | other).ids)]), mine)
        Task = self.env['advanced.project.task'].with_user(user)
        self.assertEqual(Task.search([('project_id', '=', mine.id)]), shared)
        with self.assertRaises(AccessError):
            hidden.with_user(user).read(['name'])
        Update = self.env['advanced.project.update'].with_user(user)
        self.assertEqual(Update.search([('project_id', '=', mine.id)]), published)
        with self.assertRaises(AccessError):
            draft.with_user(user).read(['name'])
        with self.assertRaises(AccessError):
            mine.with_user(user).write({'name': 'Changed'})
        # the collaborator follows the project, and can comment on it
        self.assertIn(self.customer, mine.message_partner_ids)
        mine.with_user(user).message_post(body='Hello from the customer', message_type='comment',
                                          subtype_xmlid='mail.mt_comment')

    def test_portal_user_without_customer_group_sees_nothing(self):
        user = self._portal_customer('ap_portal_only', self.customer, with_group=False)
        project = self._project(user_id=False)
        self.env['advanced.project.collaborator'].create({
            'project_id': project.id, 'partner_id': self.customer.id, 'collaborator_type': 'customer',
        })
        with self.assertRaises(AccessError):
            project.with_user(user).read(['name'])

    def test_private_comments_hidden_from_customers(self):
        user = self._portal_customer('ap_customer_private', self.customer)
        project = self._project(user_id=False)
        self.env['advanced.project.collaborator'].create({
            'project_id': project.id, 'partner_id': self.customer.id, 'collaborator_type': 'customer',
        })
        public = project.with_user(self.admin).message_post(
            body='Shared with everyone', message_type='comment', subtype_xmlid='mail.mt_comment')
        private = project.with_user(self.admin).message_post(
            body='Employees only', message_type='comment', subtype_xmlid='mail.mt_comment', is_internal=True)
        self.assertTrue(private.is_internal)
        # no notification for customers on a private comment
        self.assertNotIn(self.customer, private.notification_ids.res_partner_id)
        self.assertIn(self.customer, public.notification_ids.res_partner_id)
        Message = self.env['mail.message'].with_user(user)
        visible = Message.search([('model', '=', 'advanced.project'), ('res_id', '=', project.id)])
        self.assertIn(public, visible)
        self.assertNotIn(private, visible)
        # customers cannot make their own comments private (only employees choose)
        own = project.with_user(user).message_post(
            body='Customer note', message_type='comment', subtype_xmlid='mail.mt_comment', is_internal=True)
        self.assertFalse(own.is_internal)
        # employees switch a comment between private and public
        public.with_user(self.admin).advanced_project_set_private(True)
        self.assertTrue(public.is_internal)
        with self.assertRaises(AccessError):
            own.with_user(user).advanced_project_set_private(True)

    def test_private_flag_sent_to_employees_only(self):
        project = self._project(user_id=False)
        message = project.with_user(self.admin).message_post(
            body='Employees only', message_type='comment', subtype_xmlid='mail.mt_comment', is_internal=True)
        data = Store().add(message.with_user(self.admin)).get_result()
        self.assertTrue(data['mail.message'][0]['advanced_project_private'])

    # ------------------------------------------------------------
    # Invitations
    # ------------------------------------------------------------

    def test_invite_colleague_keeps_permissions(self):
        project = self._project(self.admin)
        groups_before = self.nobody.group_ids
        wizard = self.env['advanced.project.invite'].with_user(self.admin).create({
            'project_id': project.id, 'collaborator_type': 'colleague',
            'partner_ids': [(6, 0, self.nobody.partner_id.ids)], 'send_invitation': False,
        })
        # flagged: they have no Project permission that opens it
        self.assertTrue(wizard.has_issues)
        self.assertIn('no Project permission', wizard.access_warning)
        wizard.action_invite()
        collaborator = project.collaborator_ids.filtered(lambda c: c.partner_id == self.nobody.partner_id)
        self.assertEqual(collaborator.collaborator_type, 'colleague')
        self.assertEqual(collaborator.access_state, 'no_permission')
        self.assertEqual(self.nobody.group_ids, groups_before)

    def test_invite_customer_without_login_flags_and_fixes(self):
        project = self._project(self.admin)
        wizard = self.env['advanced.project.invite'].with_user(self.admin).create({
            'project_id': project.id, 'collaborator_type': 'customer',
            'partner_ids': [(6, 0, self.customer.ids)], 'send_invitation': False,
            'update_permissions': False,
        })
        self.assertTrue(wizard.has_issues)
        self.assertEqual(wizard.fixable_count, 1)
        self.assertTrue(wizard.can_fix_access)
        action = wizard.action_invite()
        self.assertEqual(action['tag'], 'display_notification')
        collaborator = project.collaborator_ids.filtered(lambda c: c.partner_id == self.customer)
        self.assertEqual(collaborator.access_state, 'no_user')
        self.assertTrue(collaborator.with_user(self.admin).can_fix_access)
        collaborator.with_user(self.admin).action_fix_access()
        collaborator.invalidate_recordset()
        user = self.customer.user_ids
        self.assertTrue(user and user._is_portal())
        self.assertTrue(user.has_group('advanced_projects.group_advanced_project_customer'))
        self.assertEqual(collaborator.access_state, 'ok')
        self.assertEqual(project.with_user(user).name, 'Website Launch')

    def test_invite_customer_adds_missing_group(self):
        user = self._portal_customer('ap_customer_nogroup', self.customer, with_group=False)
        project = self._project(self.admin)
        self.env['advanced.project.invite'].with_user(self.admin).create({
            'project_id': project.id, 'collaborator_type': 'customer',
            'partner_ids': [(6, 0, self.customer.ids)], 'send_invitation': True,
        }).action_invite()
        self.assertTrue(user.has_group('advanced_projects.group_advanced_project_customer'))
        self.assertEqual(project.with_user(user).name, 'Website Launch')

    def test_customer_access_needs_the_privilege(self):
        project = self._project(self.own)
        wizard = self.env['advanced.project.invite'].with_user(self.own).create({
            'project_id': project.id, 'collaborator_type': 'customer',
            'partner_ids': [(6, 0, self.customer.ids)], 'send_invitation': False,
        })
        self.assertFalse(wizard.can_fix_access)
        wizard.action_invite()
        collaborator = project.collaborator_ids.filtered(lambda c: c.partner_id == self.customer)
        self.assertEqual(collaborator.access_state, 'no_user')
        self.assertFalse(self.customer.user_ids)
        with self.assertRaises(AccessError):
            collaborator.with_user(self.own).action_fix_access()

    def test_employee_invited_as_customer_is_flagged_not_converted(self):
        project = self._project(self.admin)
        self.env['advanced.project.invite'].with_user(self.admin).create({
            'project_id': project.id, 'collaborator_type': 'customer',
            'partner_ids': [(6, 0, self.own.partner_id.ids)], 'send_invitation': False,
        }).action_invite()
        collaborator = project.collaborator_ids.filtered(lambda c: c.partner_id == self.own.partner_id)
        self.assertEqual(collaborator.access_state, 'internal_user')
        self.assertFalse(collaborator.with_user(self.admin).can_fix_access)
        with self.assertRaises(UserError):
            collaborator.with_user(self.admin).action_fix_access()
        self.assertTrue(self.own._is_internal())

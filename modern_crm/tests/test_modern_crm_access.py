from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import ModernCrmCommon

PREFIX = 'modern_crm.group_modern_crm_opportunity_'


@tagged('post_install', '-at_install')
class TestModernCrmAccess(ModernCrmCommon):
    """The per-permission access model (CLAUDE.md > Permissions)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, *perms):
            return new_test_user(cls.env, login, groups=','.join(PREFIX + p for p in perms) or
                                 'modern_crm.group_modern_crm_user')

        cls.nobody = user('crm_nobody')
        cls.creator = user('crm_creator', 'create_only')
        cls.own = user('crm_own', 'edit_own')
        cls.lead_user = user('crm_lead', 'edit_team')
        cls.member = user('crm_member', 'edit_own')
        cls.viewer = user('crm_viewer', 'view_all')
        cls.deleter = user('crm_deleter', 'edit_own', 'delete_own')
        lead_employee = cls.env['hr.employee'].create({'name': 'Lead', 'user_id': cls.lead_user.id})
        cls.env['hr.employee'].create({'name': 'Member', 'user_id': cls.member.id, 'parent_id': lead_employee.id})

    def test_no_permission_no_access(self):
        opportunity = self._opportunity()
        with self.assertRaises(AccessError):
            opportunity.with_user(self.nobody).read(['name'])
        with self.assertRaises(AccessError):
            self._opportunity(self.nobody)

    def test_create_only(self):
        opportunity = self._opportunity(self.creator)
        self.assertEqual(opportunity.with_user(self.creator).line_ids.quantity, 3)
        with self.assertRaises(AccessError):
            opportunity.with_user(self.creator).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            self._opportunity().with_user(self.creator).read(['name'])

    def test_edit_own_includes_owned(self):
        created = self._opportunity(self.own)
        owned = self._opportunity(user_id=self.own.id)
        other = self._opportunity(user_id=False)
        Opportunity = self.env['modern.crm.opportunity'].with_user(self.own)
        self.assertEqual(Opportunity.search([('id', 'in', (created | owned | other).ids)]), created | owned)
        # editing includes the products, removing them too
        owned.with_user(self.own).write({'line_ids': [(5, 0, 0)]})
        self.assertFalse(owned.line_ids)
        with self.assertRaises(AccessError):
            created.with_user(self.own).unlink()

    def test_edit_my_team(self):
        team_record = self._opportunity(self.member)
        other = self._opportunity(user_id=False)
        Opportunity = self.env['modern.crm.opportunity'].with_user(self.lead_user)
        self.assertEqual(Opportunity.search([('id', 'in', (team_record | other).ids)]), team_record)
        team_record.with_user(self.lead_user).write({'next_step': 'Call back'})

    def test_view_all(self):
        opportunity = self._opportunity(user_id=False)
        self.assertEqual(opportunity.with_user(self.viewer).name, 'Hay for winter')
        with self.assertRaises(AccessError):
            opportunity.with_user(self.viewer).write({'name': 'Changed'})

    def test_delete_own(self):
        mine = self._opportunity(self.deleter)
        other = self._opportunity(user_id=False)
        mine.with_user(self.deleter).unlink()
        with self.assertRaises(AccessError):
            other.with_user(self.deleter).unlink()

    def test_administrator_has_everything(self):
        admin = new_test_user(self.env, 'crm_admin', groups='modern_crm.group_modern_crm_manager')
        opportunity = self._opportunity(user_id=False)
        opportunity.with_user(admin).write({'name': 'Changed'})
        opportunity.with_user(admin).unlink()
        self.env['modern.crm.lost.reason'].with_user(admin).create({'name': 'Budget cut'})

    def test_workflow_actions_need_their_privilege(self):
        opportunity = self._opportunity(self.own)
        with self.assertRaises(AccessError):
            opportunity.with_user(self.own).action_new_quote()
        with self.assertRaises(AccessError):
            opportunity.with_user(self.own).action_confirm_sale()
        contract = self.env['modern.crm.contract'].create({'opportunity_id': opportunity.id})
        with self.assertRaises(AccessError):
            contract.with_user(self.own).action_send_for_signature()

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

PREFIX = 'helpdesk_management.group_helpdesk_ticket_'


@tagged('post_install', '-at_install')
class TestHelpdeskAccess(TransactionCase):
    """The per-permission access model (CLAUDE.md > Permissions)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.team = cls.env['helpdesk.team'].create({'name': 'Access Team', 'assign_method': 'manual'})

        def user(login, *perms):
            return new_test_user(cls.env, login, groups=','.join(PREFIX + p for p in perms) or
                                 'helpdesk_management.group_helpdesk_user')

        cls.nobody = user('hd_nobody')
        cls.creator = user('hd_creator', 'create_only')
        cls.own = user('hd_own', 'edit_own')
        cls.lead = user('hd_lead', 'edit_team')
        cls.member = user('hd_member', 'edit_own')
        cls.viewer = user('hd_viewer', 'view_all')
        cls.deleter = user('hd_deleter', 'edit_own', 'delete_own')
        lead_employee = cls.env['hr.employee'].create({'name': 'Lead', 'user_id': cls.lead.id})
        cls.env['hr.employee'].create({'name': 'Member', 'user_id': cls.member.id, 'parent_id': lead_employee.id})

    def _ticket(self, user=None, **vals):
        Ticket = self.env['helpdesk.ticket'].with_user(user) if user else self.env['helpdesk.ticket']
        return Ticket.create(dict({'name': 'Access test', 'team_id': self.team.id}, **vals))

    def test_no_permission_no_access(self):
        ticket = self._ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.nobody).read(['name'])
        with self.assertRaises(AccessError):
            self._ticket(self.nobody)

    def test_create_only(self):
        ticket = self._ticket(self.creator)
        self.assertEqual(ticket.with_user(self.creator).read(['name'])[0]['name'], 'Access test')
        with self.assertRaises(AccessError):
            ticket.with_user(self.creator).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            self._ticket().with_user(self.creator).read(['name'])

    def test_edit_own_includes_assigned(self):
        created = self._ticket(self.own)
        assigned = self._ticket(user_id=self.own.id)
        other = self._ticket()
        Ticket = self.env['helpdesk.ticket'].with_user(self.own)
        self.assertEqual(Ticket.search([('id', 'in', (created | assigned | other).ids)]), created | assigned)
        assigned.with_user(self.own).write({'name': 'Working on it'})
        with self.assertRaises(AccessError):
            created.with_user(self.own).unlink()

    def test_edit_my_team(self):
        team_ticket = self._ticket(self.member)
        other = self._ticket()
        Ticket = self.env['helpdesk.ticket'].with_user(self.lead)
        self.assertEqual(Ticket.search([('id', 'in', (team_ticket | other).ids)]), team_ticket)
        team_ticket.with_user(self.lead).write({'name': 'Reviewed by lead'})
        sla_status = self.env['helpdesk.sla.status'].with_user(self.lead)
        self.assertFalse(sla_status.search([('ticket_id', '=', other.id)]))

    def test_view_all(self):
        ticket = self._ticket()
        ticket.with_user(self.viewer).read(['name'])
        with self.assertRaises(AccessError):
            ticket.with_user(self.viewer).write({'name': 'Changed'})

    def test_delete_own(self):
        mine = self._ticket(self.deleter)
        other = self._ticket()
        mine.with_user(self.deleter).unlink()
        with self.assertRaises(AccessError):
            other.with_user(self.deleter).unlink()

    def test_administrator_implies_every_permission(self):
        admin_group = self.env.ref('helpdesk_management.group_helpdesk_manager')
        for code in ('create_only', 'edit_own', 'edit_team', 'edit_all', 'view_all', 'delete_own', 'delete_all'):
            self.assertIn(self.env.ref(PREFIX + code), admin_group.all_implied_ids)

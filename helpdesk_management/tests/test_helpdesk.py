from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpdesk(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.agent_1 = new_test_user(cls.env, 'hd_agent_1', groups='base.group_user,helpdesk_management.group_helpdesk_ticket_own')
        cls.agent_2 = new_test_user(cls.env, 'hd_agent_2', groups='base.group_user,helpdesk_management.group_helpdesk_ticket_own')
        cls.agent_3 = new_test_user(cls.env, 'hd_agent_3', groups='base.group_user,helpdesk_management.group_helpdesk_ticket_own')
        cls.manager = new_test_user(cls.env, 'hd_manager', groups='base.group_user,helpdesk_management.group_helpdesk_ticket_create,helpdesk_management.group_helpdesk_ticket_update,helpdesk_management.group_helpdesk_ticket_delete,helpdesk_management.group_helpdesk_team_create,helpdesk_management.group_helpdesk_team_update,helpdesk_management.group_helpdesk_team_delete,helpdesk_management.group_helpdesk_stage_create,helpdesk_management.group_helpdesk_stage_update,helpdesk_management.group_helpdesk_stage_delete,helpdesk_management.group_helpdesk_sla_create,helpdesk_management.group_helpdesk_sla_update,helpdesk_management.group_helpdesk_sla_delete,helpdesk_management.group_helpdesk_ticket_type_create,helpdesk_management.group_helpdesk_ticket_type_update,helpdesk_management.group_helpdesk_ticket_type_delete,helpdesk_management.group_helpdesk_tag_create,helpdesk_management.group_helpdesk_tag_update,helpdesk_management.group_helpdesk_tag_delete')
        cls.stage_new = cls.env.ref('helpdesk_management.stage_new')
        cls.stage_progress = cls.env.ref('helpdesk_management.stage_in_progress')
        cls.stage_hold = cls.env.ref('helpdesk_management.stage_on_hold')
        cls.stage_solved = cls.env.ref('helpdesk_management.stage_solved')
        cls.stage_cancelled = cls.env.ref('helpdesk_management.stage_cancelled')
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Test Hours', 'tz': 'UTC'})
        cls.team = cls.env['helpdesk.team'].create({
            'name': 'Test Support',
            'member_ids': [(6, 0, (cls.agent_1 | cls.agent_2 | cls.agent_3).ids)],
            'resource_calendar_id': cls.calendar.id,
        })
        cls.customer = cls.env['res.partner'].create({'name': 'Jane Customer', 'email': 'jane@example.com'})
        cls.issue = cls.env.ref('helpdesk_management.ticket_type_issue')
        cls.question = cls.env.ref('helpdesk_management.ticket_type_question')

    def _ticket(self, **vals):
        return self.env['helpdesk.ticket'].create(dict({'name': 'Printer jammed', 'team_id': self.team.id}, **vals))

    # ------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------

    def test_ticket_defaults(self):
        ticket = self._ticket(partner_id=self.customer.id)
        self.assertTrue(ticket.ticket_ref)
        self.assertEqual(ticket.stage_id, self.stage_new, 'a new ticket starts in the first stage of its team')
        self.assertEqual(ticket.partner_email, 'jane@example.com')
        self.assertEqual(ticket.display_name, f'Printer jammed (#{ticket.ticket_ref})')
        self.assertIn(self.customer, ticket.message_partner_ids, 'the customer follows the ticket')
        self.assertFalse(ticket.fold)
        self.assertFalse(ticket.close_date)
        self.assertNotEqual(self._ticket().ticket_ref, ticket.ticket_ref)

    def test_ticket_found_by_reference(self):
        ticket = self._ticket()
        found = self.env['helpdesk.ticket'].name_search(ticket.ticket_ref)
        self.assertIn(ticket.id, [res[0] for res in found])

    def test_customer_from_email(self):
        ticket = self._ticket(partner_name='New Person', partner_email='New.Person@Example.com')
        self.assertTrue(ticket.partner_id, 'a contact is created for an unknown email')
        self.assertEqual(ticket.partner_id.name, 'New Person')
        self.assertEqual(ticket.partner_id.email, 'new.person@example.com')
        again = self._ticket(partner_email='new.person@example.com')
        self.assertEqual(again.partner_id, ticket.partner_id, 'a known email reuses the contact')

    def test_close_and_reopen(self):
        ticket = self._ticket()
        ticket.stage_id = self.stage_solved
        self.assertTrue(ticket.fold)
        self.assertTrue(ticket.close_date)
        self.assertGreaterEqual(ticket.close_hours, 0)
        closed_on = ticket.close_date
        ticket.stage_id = self.stage_cancelled
        self.assertEqual(ticket.close_date, closed_on, 'moving between closing stages keeps the close date')
        ticket.stage_id = self.stage_progress
        self.assertFalse(ticket.close_date, 'reopening clears the close date')

    def test_stage_change_resets_kanban_state(self):
        ticket = self._ticket(kanban_state='blocked')
        ticket.stage_id = self.stage_progress
        self.assertEqual(ticket.kanban_state, 'normal')

    def test_change_team_resets_stage(self):
        other_stage = self.env['helpdesk.stage'].create({'name': 'Triage', 'sequence': 1})
        other_team = self.env['helpdesk.team'].create({'name': 'Other', 'stage_ids': [(6, 0, other_stage.ids)]})
        ticket = self._ticket()
        ticket.team_id = other_team
        self.assertEqual(ticket.stage_id, other_stage)

    def test_assign_date(self):
        ticket = self._ticket()
        self.assertFalse(ticket.assign_date)
        ticket.user_id = self.agent_1
        first = ticket.assign_date
        self.assertTrue(first)
        ticket.user_id = self.agent_2
        self.assertEqual(ticket.assign_date, first, 'the first assignment date is kept')

    # ------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------

    def test_manual_assignment(self):
        self.assertFalse(self._ticket().user_id)

    def test_round_robin_assignment(self):
        self.team.assign_method = 'randomly'
        users = [self._ticket().user_id for _i in range(6)]
        self.assertEqual(set(users[:3]), set(self.team.member_ids), 'each member gets one of the first three')
        self.assertEqual(users[:3], users[3:], 'then the turn goes round again')

    def test_balanced_assignment(self):
        self.team.assign_method = 'balanced'
        self._ticket(user_id=self.agent_1.id)
        self._ticket(user_id=self.agent_1.id)
        self._ticket(user_id=self.agent_2.id)
        self.assertEqual(self._ticket().user_id, self.agent_3)
        self.assertEqual(self._ticket().user_id, self.agent_2)
        closed = self._ticket(user_id=self.agent_1.id)
        closed.stage_id = self.stage_solved
        # open tickets: agent_1 2, agent_2 2, agent_3 1
        self.assertEqual(self._ticket().user_id, self.agent_3, 'closed tickets do not count')

    def test_assign_to_me(self):
        ticket = self._ticket()
        ticket.with_user(self.agent_2).action_assign_to_me()
        self.assertEqual(ticket.user_id, self.agent_2)

    # ------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------

    def _sla(self, **vals):
        return self.env['helpdesk.sla'].create(dict({
            'name': 'Answer within 4 hours',
            'team_id': self.team.id,
            'stage_id': self.stage_progress.id,
            'time': 4,
        }, **vals))

    def test_sla_applies_by_criteria(self):
        urgent_sla = self._sla(name='Urgent', priority='3')
        issue_sla = self._sla(name='Issues', ticket_type_ids=[(6, 0, self.issue.ids)])
        customer_sla = self._sla(name='VIP', partner_ids=[(6, 0, self.customer.ids)])
        general_sla = self._sla(name='All')

        ticket = self._ticket()
        self.assertEqual(ticket.sla_status_ids.sla_id, general_sla)

        ticket.write({'priority': '3', 'ticket_type_id': self.issue.id})
        self.assertEqual(ticket.sla_status_ids.sla_id, general_sla | urgent_sla | issue_sla)

        contact = self.env['res.partner'].create({'name': 'Jane Colleague', 'parent_id': self.customer.id})
        ticket.write({'partner_id': contact.id, 'priority': '0'})
        self.assertEqual(ticket.sla_status_ids.sla_id, general_sla | issue_sla | customer_sla,
                         "a customer's contacts get the customer's SLA; dropping the priority removes the urgent SLA")

    def test_sla_tags(self):
        tag_billing = self.env['helpdesk.tag'].create({'name': 'Billing'})
        tag_other = self.env['helpdesk.tag'].create({'name': 'Other'})
        sla = self._sla(tag_ids=[(6, 0, tag_billing.ids)])
        ticket = self._ticket(tag_ids=[(6, 0, tag_other.ids)])
        self.assertFalse(ticket.sla_status_ids)
        ticket.tag_ids = [(4, tag_billing.id)]
        self.assertEqual(ticket.sla_status_ids.sla_id, sla)

    def test_sla_disabled_on_team(self):
        self._sla()
        self.team.use_sla = False
        self.assertFalse(self._ticket().sla_status_ids)

    def test_sla_deadline_uses_working_hours(self):
        self._sla(time=4)
        ticket = self._ticket()
        expected = self.calendar.plan_hours(4, ticket.create_date, compute_leaves=True)
        self.assertEqual(ticket.sla_status_ids.deadline, expected.replace(tzinfo=None))
        self.assertEqual(ticket.sla_deadline, ticket.sla_status_ids.deadline)

    def test_sla_reached_on_time(self):
        self._sla(time=4)
        ticket = self._ticket()
        status = ticket.sla_status_ids
        self.assertEqual(status.status, 'ongoing')
        ticket.stage_id = self.stage_hold  # a stage after the target also reaches it
        self.assertTrue(status.reached_datetime)
        self.assertEqual(status.status, 'reached')
        self.assertFalse(ticket.sla_deadline)
        self.assertFalse(ticket.sla_fail)
        self.assertTrue(ticket.sla_success)
        self.assertIn(ticket, self.env['helpdesk.ticket'].search([('sla_success', '=', True)]))

        ticket.stage_id = self.stage_new
        self.assertFalse(status.reached_datetime, 'going back before the target stage restarts the SLA')

    def test_sla_failed(self):
        self._sla(time=4)
        ticket = self._ticket()
        Ticket = self.env['helpdesk.ticket']
        Status = self.env['helpdesk.sla.status']
        self.assertNotIn(ticket, Ticket.search([('sla_fail', '=', True)]))
        self.assertIn(ticket, Ticket.search([('sla_fail', '=', False)]))
        self.assertIn(ticket.sla_status_ids, Status.search([('status', 'in', ['ongoing'])]))

        with freeze_time(fields.Datetime.now() + timedelta(days=30)):
            ticket.invalidate_recordset(['sla_fail'])
            ticket.sla_status_ids.invalidate_recordset(['status'])
            self.assertTrue(ticket.sla_fail)
            self.assertEqual(ticket.sla_status_ids.status, 'failed')
            self.assertIn(ticket, Ticket.search([('sla_fail', '=', True)]))
            self.assertNotIn(ticket, Ticket.search([('sla_fail', '=', False)]))
            self.assertIn(ticket.sla_status_ids, Status.search([('status', 'in', ['failed'])]))
            self.assertEqual(self.team.sla_failed_ticket_count, 1)

            ticket.stage_id = self.stage_progress
            status = ticket.sla_status_ids
            self.assertTrue(status.reached_late)
            self.assertEqual(status.status, 'failed', 'reached after the deadline is still failed')
            self.assertGreater(status.exceeded_hours, 0)
            self.assertTrue(ticket.sla_fail)
            self.assertIn(ticket, Ticket.search([('sla_fail', '=', True)]))
            self.assertIn(status, Status.search([('status', 'in', ['failed'])]))
            self.assertNotIn(status, Status.search([('status', 'in', ['reached'])]))

    def test_reached_sla_kept_when_criteria_change(self):
        sla = self._sla(priority='3')
        ticket = self._ticket(priority='3')
        ticket.stage_id = self.stage_progress
        ticket.priority = '0'
        self.assertEqual(ticket.sla_status_ids.sla_id, sla, 'a reached SLA stays as history')

    # ------------------------------------------------------------
    # Team
    # ------------------------------------------------------------

    def test_team_dashboard_counts(self):
        self._ticket(user_id=self.agent_1.id, priority='3')
        self._ticket()
        self._ticket().stage_id = self.stage_solved
        team = self.team.with_user(self.agent_1)
        self.assertEqual(team.open_ticket_count, 2)
        self.assertEqual(team.unassigned_ticket_count, 1)
        self.assertEqual(team.urgent_ticket_count, 1)
        self.assertEqual(team.my_ticket_count, 1)

    def test_team_alias_creates_tickets_for_team(self):
        self.team.alias_name = 'test-support'
        self.assertEqual(self.team.alias_id.alias_model_id.model, 'helpdesk.ticket')
        self.assertIn(f"'team_id': {self.team.id}", self.team.alias_id.alias_defaults)

    def test_team_default_stages(self):
        team = self.env['helpdesk.team'].create({'name': 'Fresh Team'})
        self.assertEqual(team.stage_ids,
                         self.stage_new | self.stage_progress | self.stage_hold | self.stage_solved | self.stage_cancelled)

    def test_auto_close(self):
        self.team.write({
            'auto_close_ticket': True,
            'auto_close_day': 5,
            'from_stage_ids': [(6, 0, self.stage_hold.ids)],
            'to_stage_id': self.stage_solved.id,
        })
        on_hold = self._ticket(stage_id=self.stage_hold.id)
        in_progress = self._ticket(stage_id=self.stage_progress.id)
        with freeze_time(fields.Datetime.now() + timedelta(days=6)):
            self.env['helpdesk.team']._cron_auto_close_tickets()
        self.assertEqual(on_hold.stage_id, self.stage_solved)
        self.assertTrue(on_hold.close_date)
        self.assertEqual(in_progress.stage_id, self.stage_progress, 'only tickets in the chosen stages close')

    def test_auto_close_needs_target_stage(self):
        with self.assertRaises(ValidationError):
            self.team.write({'auto_close_ticket': True, 'to_stage_id': False})

    # ------------------------------------------------------------
    # Mail and rating
    # ------------------------------------------------------------

    def test_ticket_from_email(self):
        alias_domain = self.env['mail.alias.domain'].create({'name': 'helpdesk.example.com'})
        self.team.write({'alias_name': 'test-support', 'alias_domain_id': alias_domain.id})
        alias_email = 'test-support@helpdesk.example.com'
        message = (
            'Return-Path: <someone@example.org>\n'
            'To: %s\n'
            'From: "Sam Sender" <sam@example.org>\n'
            'Subject: Cannot log in\n'
            'Message-ID: <helpdesk-test-1@example.org>\n'
            'Content-Type: text/plain\n\n'
            'My password does not work.\n'
        ) % alias_email
        ticket_id = self.env['mail.thread'].message_process('helpdesk.ticket', message)
        ticket = self.env['helpdesk.ticket'].browse(ticket_id)
        self.assertEqual(ticket.name, 'Cannot log in')
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id.email, 'sam@example.org')
        self.assertIn('My password does not work.', str(ticket.description))

    def test_stage_template_sent(self):
        template = self.env.ref('helpdesk_management.ticket_received_email_template')
        ticket = self.env['helpdesk.ticket'].with_context(tracking_disable=False).create({
            'name': 'Hello', 'team_id': self.team.id, 'partner_id': self.customer.id,
        })
        self.env.flush_all()
        self.env.cr.precommit.run()
        messages = ticket.message_ids.filtered(lambda m: m.subject and ticket.ticket_ref in m.subject)
        self.assertTrue(messages, 'the stage template (%s) is sent to the customer' % template.name)

    def test_rating_request(self):
        self.team.use_rating = True
        ticket = self._ticket(partner_id=self.customer.id)
        ticket.stage_id = self.stage_solved
        rating = self.env['rating.rating'].search([('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id)])
        self.assertTrue(rating, 'moving to Solved asks the customer for a rating')
        self.assertEqual(rating.partner_id, self.customer)
        self.assertEqual(rating.parent_res_model, 'helpdesk.team')
        ticket.rating_apply(5, token=rating.access_token)
        self.assertEqual(ticket.rating_last_value, 5)
        self.assertEqual(self.team.rating_percentage_satisfaction, 100)

    def test_no_rating_request_when_disabled(self):
        ticket = self._ticket(partner_id=self.customer.id)
        ticket.stage_id = self.stage_solved
        self.assertFalse(self.env['rating.rating'].search([('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id)]))

    # ------------------------------------------------------------
    # Portal and access
    # ------------------------------------------------------------

    def test_portal_close(self):
        ticket = self._ticket(partner_id=self.customer.id)
        with self.assertRaises(UserError):
            ticket.action_portal_close()
        self.team.allow_portal_ticket_closing = True
        ticket.action_portal_close()
        self.assertEqual(ticket.stage_id, self.stage_solved)

    def test_portal_user_sees_company_tickets(self):
        company = self.env['res.partner'].create({'name': 'Acme', 'is_company': True})
        contact_a = self.env['res.partner'].create({'name': 'Ann', 'email': 'ann@acme.test', 'parent_id': company.id})
        contact_b = self.env['res.partner'].create({'name': 'Bob', 'email': 'bob@acme.test', 'parent_id': company.id})
        portal_user = new_test_user(self.env, 'hd_portal', groups='base.group_portal', partner_id=contact_a.id)
        own = self._ticket(partner_id=contact_a.id)
        colleague = self._ticket(partner_id=contact_b.id)
        other = self._ticket(partner_id=self.customer.id)
        visible = self.env['helpdesk.ticket'].with_user(portal_user).search([])
        self.assertEqual(visible, own | colleague)
        with self.assertRaises(AccessError):
            other.with_user(portal_user).read(['name'])
        with self.assertRaises(AccessError):
            own.with_user(portal_user).write({'name': 'Changed'})

    def test_access_rights(self):
        with self.assertRaises(AccessError):
            self.env['helpdesk.team'].with_user(self.agent_1).create({'name': 'Agents cannot configure'})
        with self.assertRaises(AccessError):
            self._ticket().with_user(self.agent_1).unlink()
        self._ticket().with_user(self.manager).unlink()
        ticket_type = self.env['helpdesk.ticket.type'].with_user(self.manager).create({'name': 'Complaint'})
        self.assertTrue(ticket_type)

    def test_partner_ticket_count(self):
        contact = self.env['res.partner'].create({'name': 'Jane Colleague', 'parent_id': self.customer.id})
        self._ticket(partner_id=self.customer.id)
        self._ticket(partner_id=contact.id)
        self.customer.invalidate_recordset(['helpdesk_ticket_count'])
        self.assertEqual(self.customer.helpdesk_ticket_count, 2, "a company's count includes its contacts")
        self.assertEqual(contact.helpdesk_ticket_count, 1)

    def test_form_create(self):
        form = Form(self.env['helpdesk.ticket'].with_context(default_team_id=self.team.id))
        form.name = 'From the form'
        form.partner_id = self.customer
        ticket = form.save()
        self.assertEqual(ticket.partner_email, self.customer.email)
        self.assertEqual(ticket.stage_id, self.stage_new)

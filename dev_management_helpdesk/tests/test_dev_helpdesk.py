from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDevHelpdesk(TransactionCase):

    def test_create_dev_tickets_from_helpdesk(self):
        team = self.env['helpdesk.team'].create({'name': 'Support'})
        helpdesk_ticket = self.env['helpdesk.ticket'].create({
            'name': 'Export crashes', 'team_id': team.id, 'priority': '3', 'description': '<p>Steps...</p>'})
        action = helpdesk_ticket.action_create_dev_tickets()
        wizard_form = Form(self.env['dev.ticket.from.helpdesk'].with_context(action['context']))
        with wizard_form.line_ids.new() as line:
            line.name = 'Add a retry'
        wizard = wizard_form.save()
        self.assertEqual(len(wizard.line_ids), 2)
        first = wizard.line_ids[0]
        self.assertEqual(first.name, 'Export crashes')
        self.assertEqual(first.type_id, self.env.ref('dev_management.ticket_type_bug'))
        self.assertEqual(first.priority_id, self.env.ref('dev_management.priority_highest'))
        wizard.action_create()
        self.assertEqual(len(helpdesk_ticket.dev_ticket_ids), 2)
        dev_ticket = helpdesk_ticket.dev_ticket_ids.filtered(lambda t: t.name == 'Export crashes')
        self.assertIn('Steps', dev_ticket.description)
        self.assertEqual(dev_ticket.helpdesk_ticket_ids, helpdesk_ticket)
        notes = helpdesk_ticket.message_ids
        dev_ticket.stage_id = self.env.ref('dev_management.ticket_stage_done')
        new_notes = helpdesk_ticket.message_ids - notes
        self.assertTrue(any('is done' in (m.body or '') for m in new_notes))

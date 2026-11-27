from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSuggestionHelpdesk(TransactionCase):

    def test_suggestion_from_helpdesk(self):
        customer = self.env['res.partner'].create({'name': 'Customer'})
        team = self.env['helpdesk.team'].create({'name': 'Support'})
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Can we have dark mode?', 'team_id': team.id, 'partner_id': customer.id})
        context = ticket.action_create_suggestion()['context']
        wizard = Form(self.env['dev.suggestion.from.helpdesk'].with_context(context)).save()
        self.assertEqual(wizard.partner_id, customer)
        suggestion = self.env['dev.suggestion'].browse(wizard.action_confirm()['res_id'])
        self.assertEqual(suggestion.name, 'Can we have dark mode?')
        self.assertEqual(suggestion.vote_ids.partner_id, customer)
        self.assertEqual(suggestion.source_id, self.env.ref('dev_feature_suggestions.source_helpdesk'))
        self.assertEqual(ticket.suggestion_ids, suggestion)

        # A second customer asking the same thing votes on it.
        other = self.env['res.partner'].create({'name': 'Other'})
        ticket2 = self.env['helpdesk.ticket'].create({'name': 'Dark theme', 'team_id': team.id, 'partner_id': other.id})
        form = Form(self.env['dev.suggestion.from.helpdesk'].with_context(ticket2.action_create_suggestion()['context']))
        form.link_existing = True
        form.suggestion_id = suggestion
        form.importance_id = self.env.ref('dev_feature_suggestions.importance_critical')
        form.save().action_confirm()
        self.assertEqual(suggestion.vote_count, 2)
        self.assertEqual(suggestion.helpdesk_ticket_ids, ticket | ticket2)

from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

AI_PATH = 'odoo.addons.helpdesk_management.models.helpdesk_ticket.ai_request_json'


@tagged('post_install', '-at_install')
class TestHelpdeskMetrics(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.agent = new_test_user(cls.env, 'hd_metrics_agent',
                                  groups='helpdesk_management.group_helpdesk_ticket_edit_all')
        cls.team = cls.env['helpdesk.team'].create({'name': 'Metrics Team', 'member_ids': [(6, 0, cls.agent.ids)]})
        cls.other_team = cls.env['helpdesk.team'].create({'name': 'Billing Desk (test)', 'member_ids': [(6, 0, cls.agent.ids)]})
        cls.solved = cls.env.ref('helpdesk_management.stage_solved')
        cls.issue = cls.env.ref('helpdesk_management.ticket_type_issue')
        cls.negative = cls.env.ref('helpdesk_management.sentiment_negative')
        cls.positive = cls.env.ref('helpdesk_management.sentiment_positive')
        cls.product = cls.env['product.product'].create({'name': 'Widget Pro', 'sale_ok': True})
        cls.params = cls.env['ir.config_parameter'].sudo()
        cls.params.set_param('claude_ai_settings.api_key', '')
        cls.params.set_param('claude_ai_settings.gemini_api_key', '')

    def _ticket(self, **vals):
        return self.env['helpdesk.ticket'].create(dict({'name': 'Broken widget', 'team_id': self.team.id}, **vals))

    # ------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------

    def test_defaults(self):
        ticket = self._ticket(product_ids=[(6, 0, self.product.ids)])
        self.assertEqual(ticket.source_id, self.env.ref('helpdesk_management.ticket_source_direct'))
        self.assertTrue(ticket.date_raised)
        self.assertEqual(ticket.product_ids, self.product)
        self.assertFalse(ticket.days_to_resolution)
        self.assertFalse(ticket.ai_state, 'nothing is sent to an AI without a key')

    def test_days_open_and_resolution(self):
        raised = datetime(2026, 3, 1, 9, 0)
        with freeze_time(raised):
            ticket = self._ticket(date_raised=raised)
        with freeze_time(raised + timedelta(days=3, hours=12)):
            self.env['helpdesk.ticket']._cron_refresh_days_open()
            self.assertAlmostEqual(ticket.days_open, 3.5)
            self.assertFalse(ticket.days_to_resolution)
            ticket.stage_id = self.solved
            self.assertAlmostEqual(ticket.days_to_resolution, 3.5)
            self.assertAlmostEqual(ticket.days_open, 3.5)
        with freeze_time(raised + timedelta(days=10)):
            self.env['helpdesk.ticket']._cron_refresh_days_open()
            self.assertAlmostEqual(ticket.days_open, 3.5, 'a closed ticket stops counting')

    def test_sentiment_score(self):
        ticket = self._ticket(sentiment_id=self.negative.id)
        self.assertEqual(ticket.sentiment_score, 2)

    def test_email_date_raised(self):
        message = (
            'To: support@example.com\n'
            'From: "Sam Sender" <sam@example.org>\n'
            'Subject: Order missing\n'
            'Date: Mon, 05 Oct 2026 08:30:00 +0000\n'
            'Message-ID: <helpdesk-metrics-1@example.org>\n'
            'Content-Type: text/plain\n\n'
            'Where is my order?\n'
        )
        ticket = self.env['helpdesk.ticket'].browse(
            self.env['mail.thread'].message_process('helpdesk.ticket', message))
        self.assertEqual(ticket.date_raised, datetime(2026, 10, 5, 8, 30))
        self.assertEqual(ticket.source_id, self.env.ref('helpdesk_management.ticket_source_email'))

    # ------------------------------------------------------------
    # AI triage
    # ------------------------------------------------------------

    def _ai_answer(self, **extra):
        return dict({
            'team': 'Billing Desk (test)',
            'ticket_type': 'issue',
            'tags': [],
            'priority': 'High',
            'products': ['widget pro', 'Not A Product'],
            'sentiment': 'Negative',
            'sentiment_reason': 'The customer sounds frustrated.',
            'recommended_actions': ['Apologise for the delay', 'Ship a replacement <today>'],
        }, **extra)

    def test_ai_queued_when_key_set(self):
        self.params.set_param('claude_ai_settings.api_key', 'test-key')
        ticket = self._ticket()
        self.assertEqual(ticket.ai_state, 'pending')
        self.assertTrue(ticket.ai_available)

    def test_ai_fills_missing_details(self):
        self.params.set_param('claude_ai_settings.api_key', 'test-key')
        ticket = self.env['helpdesk.ticket'].create({'name': 'Charged twice', 'team_id': False})
        with patch(AI_PATH, return_value=self._ai_answer()) as ai:
            ticket._ai_analyse()
        prompt = ai.call_args.args[1]
        self.assertIn('Charged twice', prompt)
        self.assertIn('"Billing Desk (test)"', prompt)
        self.assertEqual(ticket.team_id, self.other_team)
        self.assertEqual(ticket.ticket_type_id, self.issue, 'names match whatever their case')
        self.assertEqual(ticket.priority, '2')
        self.assertEqual(ticket.product_ids, self.product, 'unknown products are ignored')
        self.assertEqual(ticket.sentiment_id, self.negative)
        self.assertEqual(ticket.sentiment_reason, 'The customer sounds frustrated.')
        self.assertIn('<li>Apologise for the delay</li>', str(ticket.ai_recommended_actions))
        self.assertNotIn('<today>', str(ticket.ai_recommended_actions), 'actions are escaped')
        self.assertEqual(ticket.ai_state, 'done')

    def test_ai_keeps_given_details(self):
        self.params.set_param('claude_ai_settings.api_key', 'test-key')
        question = self.env.ref('helpdesk_management.ticket_type_question')
        ticket = self._ticket(ticket_type_id=question.id, priority='1', product_ids=[(6, 0, self.product.ids)])
        with patch(AI_PATH, return_value=self._ai_answer(products=[])):
            ticket._ai_analyse()
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.ticket_type_id, question)
        self.assertEqual(ticket.priority, '1')
        self.assertEqual(ticket.product_ids, self.product)
        self.assertEqual(ticket.sentiment_id, self.negative, 'the sentiment is always estimated')

    def test_ai_failure_kept_on_ticket(self):
        self.params.set_param('claude_ai_settings.api_key', 'test-key')
        ticket = self._ticket()
        with patch(AI_PATH, side_effect=UserError('Claude API error (500): boom')):
            ticket._ai_analyse_safe()
        self.assertEqual(ticket.ai_state, 'failed')
        self.assertIn('boom', ticket.ai_error)

    def test_ai_action_needs_key(self):
        ticket = self._ticket()
        with self.assertRaises(UserError):
            ticket.action_ai_analyse()

    def test_ai_job_info(self):
        self.params.set_param('claude_ai_settings.api_key', 'test-key')
        info = self._ticket(ticket_type_id=self.issue.id).get_ai_job_info()
        self.assertEqual(info['provider'], 'Claude')
        self.assertIn('Products', info['missing'])
        self.assertNotIn('Type', info['missing'])

    # ------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------

    @freeze_time('2026-10-24 10:00:00')
    def test_dashboard_data(self):
        Ticket = self.env['helpdesk.ticket'].with_user(self.agent)
        self._ticket(user_id=self.agent.id, sentiment_id=self.negative.id, date_raised='2026-10-20 10:00:00')
        self._ticket(user_id=self.agent.id, sentiment_id=self.positive.id, date_raised='2026-10-21 10:00:00')
        self._ticket(user_id=self.agent.id, sentiment_id=self.positive.id, date_raised='2026-02-10 10:00:00')
        self._ticket(user_id=self.agent.id, sentiment_id=self.negative.id, date_raised='2025-12-15 10:00:00')
        self._ticket(team_id=self.other_team.id, sentiment_id=self.negative.id)
        self._ticket(user_id=self.agent.id).stage_id = self.solved
        data = Ticket.get_dashboard_data()
        self.assertEqual(data['my_open_count'], 4)
        teams = {row['name']: row['count'] for row in data['by_team']}
        self.assertEqual(teams['Metrics Team'], 4)
        self.assertEqual(teams['Billing Desk (test)'], 1)
        self.assertEqual(sum(row['count'] for row in data['by_company']), data['open_count'])

        months = data['charts']['last_12_months']
        self.assertEqual(len(months['labels']), 12)
        self.assertEqual(months['labels'][0], '11/2025')
        self.assertEqual(months['labels'][-1], '10/2026')
        self.assertEqual(months['values'][-1], 3.0, 'October: one negative (2) and one positive (4)')
        self.assertEqual(months['ticket_count'], 4, 'only my tickets with a sentiment count')
        ytd = data['charts']['year_to_date']
        self.assertEqual(len(ytd['labels']), 10)
        self.assertEqual(ytd['ticket_count'], 3)
        days = data['charts']['last_30_days']
        self.assertEqual(len(days['labels']), 30)
        self.assertEqual(days['labels'][-1], '24/10/2026')
        self.assertEqual(days['ticket_count'], 2)
        self.assertEqual(days['average'], 3.0)

    # ------------------------------------------------------------
    # Reports menu
    # ------------------------------------------------------------

    def test_reports_menu_hidden_until_it_has_reports(self):
        menu = self.env.ref('helpdesk_management.menu_helpdesk_reports')
        Menu = self.env['ir.ui.menu'].with_user(self.agent)
        self.assertNotIn(menu.id, Menu._visible_menu_ids(), 'an empty Reports menu is hidden')
        action = self.env['ir.actions.act_url'].create({'name': 'Ticket export', 'url': '/report/1'})
        self.env['ir.ui.menu'].create({
            'name': 'Ticket export', 'parent_id': menu.id, 'action': f'ir.actions.act_url,{action.id}'})
        self.env.registry.clear_cache()
        self.assertIn(menu.id, Menu._visible_menu_ids())

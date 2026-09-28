from odoo import http
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['helpdesk.team'].create({
            'name': 'Web Support',
            'use_website_form': True,
            'allow_portal_ticket_closing': True,
        })
        cls.customer = cls.env['res.partner'].create({'name': 'Portal Pat', 'email': 'pat@example.com'})
        cls.portal_user = new_test_user(cls.env, 'hd_portal_pat', groups='base.group_portal',
                                        partner_id=cls.customer.id, password='hd_portal_pat')

    def test_public_form_creates_ticket(self):
        self.authenticate(None, None)
        response = self.url_open(f'/helpdesk/{self.team.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Submit a Ticket', response.text)

        response = self.url_open(f'/helpdesk/{self.team.id}/submit', data={
            'csrf_token': http.Request.csrf_token(self),
            'partner_name': 'Walk In',
            'partner_email': 'walk.in@example.com',
            'name': 'Website question',
            'description': 'Line one\nLine <two>',
        })
        self.assertEqual(response.status_code, 200)
        ticket = self.env['helpdesk.ticket'].search([('name', '=', 'Website question')])
        self.assertEqual(len(ticket), 1)
        self.assertIn(ticket.ticket_ref, response.text)
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id.email, 'walk.in@example.com')
        self.assertIn('&lt;two&gt;', str(ticket.description), 'the description is escaped')

    def test_public_form_validation_and_honeypot(self):
        self.authenticate(None, None)
        response = self.url_open(f'/helpdesk/{self.team.id}/submit', data={
            'csrf_token': http.Request.csrf_token(self),
            'partner_name': 'Walk In',
            'partner_email': 'not-an-email',
            'name': 'Bad email',
        })
        self.assertIn('Please enter a valid email address.', response.text)
        self.url_open(f'/helpdesk/{self.team.id}/submit', data={
            'csrf_token': http.Request.csrf_token(self),
            'partner_name': 'Bot',
            'partner_email': 'bot@example.com',
            'name': 'Spam',
            'website_url': 'http://spam.example.com',
        })
        self.assertFalse(self.env['helpdesk.ticket'].search([('name', 'in', ['Bad email', 'Spam'])]))

    def test_form_hidden_for_teams_without_it(self):
        self.team.use_website_form = False
        response = self.url_open(f'/helpdesk/{self.team.id}', allow_redirects=False)
        self.assertEqual(response.status_code, 303)

    def test_my_tickets(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'My portal ticket', 'team_id': self.team.id, 'partner_id': self.customer.id,
        })
        other = self.env['helpdesk.ticket'].create({'name': 'Someone else', 'team_id': self.team.id})
        self.authenticate('hd_portal_pat', 'hd_portal_pat')

        response = self.url_open('/my/tickets')
        self.assertEqual(response.status_code, 200)
        self.assertIn('My portal ticket', response.text)
        self.assertNotIn('Someone else', response.text)

        response = self.url_open(f'/my/tickets/{ticket.id}')
        self.assertIn('My portal ticket', response.text)
        self.assertIn('Close this ticket', response.text)

        response = self.url_open(f'/my/tickets/{other.id}', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

        self.url_open(f'/my/tickets/{ticket.id}/close', data={'csrf_token': http.Request.csrf_token(self)})
        self.assertTrue(ticket.fold)

    def test_ticket_by_access_token(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Shared by link', 'team_id': self.team.id, 'partner_id': self.customer.id,
        })
        response = self.url_open(ticket.get_portal_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('Shared by link', response.text)

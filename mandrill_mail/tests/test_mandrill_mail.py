import base64
import hmac
import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.mandrill_api import MandrillAPI, mandrill_signature

RAW_REPLY = """From: Customer <customer@client.test>
To: {to}
Subject: Re: Your quote
Message-Id: <reply-1@client.test>
Date: Wed, 30 Sep 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

Thanks, looks good.
"""


@tagged('post_install', '-at_install')
class TestMandrillMail(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('mandrill_mail.enabled', 'True')
        ICP.set_param('mandrill_mail.api_key', 'test-key')
        ICP.set_param('mandrill_mail.reply_tracking', 'True')
        ICP.set_param('mandrill_mail.default_reply_to', 'hello@example.com')
        cls.alias_domain = cls.env['mail.alias.domain'].create({
            'name': 'example.com', 'catchall_alias': 'catchall', 'bounce_alias': 'bounce',
        })
        cls.env.company.alias_domain_id = cls.alias_domain
        cls.partner = cls.env['res.partner'].create({'name': 'Client', 'email': 'customer@client.test'})
        cls.env['mandrill.reply.route'].create({
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'email': 'crm@example.com',
        })

    def _send_mail(self, results=None):
        mail = self.env['mail.mail'].create({
            'model': 'res.partner',
            'res_id': self.partner.id,
            'subject': 'Your quote',
            'body_html': '<p>Hello</p>',
            'email_from': 'sales@example.com',
            'email_to': 'customer@client.test',
        })
        calls = []

        def fake_call(api, endpoint, **params):
            calls.append((endpoint, params))
            return results if results is not None else [
                {'email': 'customer@client.test', 'status': 'sent', '_id': 'abc123'}]

        with patch.object(type(self.env['ir.mail_server']), '_disable_send', return_value=False), \
                patch.object(MandrillAPI, 'call', fake_call):
            mail.send(raise_exception=False)
        return mail, calls

    def test_settings_turn_off_other_servers(self):
        settings = self.env['res.config.settings'].new({
            'external_email_server_default': True,
            'module_google_gmail': True,
            'module_microsoft_outlook': True,
        })
        settings.mandrill_enabled = True
        settings._onchange_mandrill_enabled()
        self.assertFalse(settings.external_email_server_default)
        self.assertFalse(settings.module_google_gmail)
        self.assertFalse(settings.module_microsoft_outlook)

    def test_send_uses_model_reply_to_metadata_and_logs(self):
        mail, calls = self._send_mail()
        self.assertEqual(mail.state, 'sent')
        endpoint, params = calls[0]
        self.assertEqual(endpoint, 'messages/send-raw')
        self.assertEqual(params['to'], [{'email': 'customer@client.test'}])
        raw = params['raw_message']
        self.assertNotIn('X-Odoo-Mandrill', raw)

        log = self.env['mandrill.mail.log'].search([('mandrill_id', '=', 'abc123')])
        self.assertEqual(log.state, 'sent')
        self.assertEqual((log.res_model, log.res_id), ('res.partner', self.partner.id))
        self.assertTrue(log.reply_token)
        self.assertIn(f'crm+odoo-{log.reply_token}@example.com', log.reply_to)
        metadata = json.loads(log.metadata)
        self.assertEqual(metadata['odoo_model'], 'res.partner')
        self.assertEqual(metadata['odoo_res_id'], str(self.partner.id))
        self.assertEqual(metadata['odoo_ref'], log.reply_token)

    def test_send_rejected_marks_mail_failed(self):
        mail, _calls = self._send_mail(results=[
            {'email': 'customer@client.test', 'status': 'rejected', '_id': 'rej1', 'reject_reason': 'hard-bounce'}])
        self.assertEqual(mail.state, 'exception')
        log = self.env['mandrill.mail.log'].search([('mandrill_id', '=', 'rej1')])
        self.assertEqual(log.state, 'rejected')
        self.assertEqual(log.error_message, 'hard-bounce')

    def test_reply_to_token_attaches_reply_to_record(self):
        self._send_mail()
        sent = self.env['mandrill.mail.log'].search([('mandrill_id', '=', 'abc123')])
        address = f'crm+odoo-{sent.reply_token}@example.com'
        with patch.object(type(self.env['ir.cron']), '_trigger'):
            logs = self.env['mandrill.service']._receive_inbound_events([{
                'event': 'inbound',
                'msg': {
                    'raw_msg': RAW_REPLY.format(to=address),
                    'email': address,
                    'to': [[address, None]],
                    'from_email': 'customer@client.test',
                    'subject': 'Re: Your quote',
                    'headers': {'Message-Id': '<reply-1@client.test>'},
                },
            }])
        self.assertEqual(logs.state, 'received')
        logs._process_inbound()
        self.assertEqual(logs.state, 'processed', logs.error_message)
        self.assertEqual((logs.res_model, logs.res_id), ('res.partner', self.partner.id))
        self.assertEqual(logs.source_log_id, sent)
        self.assertIn('looks good', logs.mail_message_id.body)

    def test_events_update_log(self):
        self._send_mail()
        log = self.env['mandrill.mail.log'].search([('mandrill_id', '=', 'abc123')])
        self.env['mandrill.service']._process_events([
            {'event': 'open', 'ts': 1790000000, 'msg': {'_id': 'abc123'}},
            {'event': 'hard_bounce', 'ts': 1790000100,
             'msg': {'_id': 'abc123', 'email': 'customer@client.test', 'bounce_description': 'bad_mailbox'}},
        ])
        self.assertEqual(log.open_count, 1)
        self.assertEqual(log.state, 'bounced')
        self.assertEqual(log.error_message, 'bad_mailbox')
        self.assertEqual(self.partner.message_bounce, 1)

    def test_route_patterns_follow_aliases(self):
        self.env['mail.alias'].create({
            'alias_name': 'support',
            'alias_domain_id': self.alias_domain.id,
            'alias_model_id': self.env['ir.model']._get_id('res.partner'),
        })
        patterns = self.env['mandrill.service']._desired_route_patterns()['example.com']
        for expected in ('support', 'support+*', 'catchall', 'bounce', 'crm', 'crm+*', 'hello', 'hello+*'):
            self.assertIn(expected, patterns)

    def test_signature(self):
        params = {'mandrill_events': '[]'}
        signature = mandrill_signature('secret', 'https://odoo.test/mandrill_mail/events', params)
        expected = hmac.new(b'secret', b'https://odoo.test/mandrill_mail/eventsmandrill_events[]', 'sha1')
        self.assertEqual(signature, base64.b64encode(expected.digest()).decode())

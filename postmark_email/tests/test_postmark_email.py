import base64
import json
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.postmark_email.models import postmark_api

REQUEST = 'odoo.addons.postmark_email.models.postmark_api.requests.request'


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = json.dumps(data)
        self.reason = 'OK'

    def json(self):
        return self._data


class PostmarkCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('postmark_email.enabled', True)
        ICP.set_param('postmark_email.server_token', 'server-token')
        ICP.set_param('postmark_email.record_routing', True)
        ICP.set_param('postmark_email.webhook_user', 'postmark')
        ICP.set_param('postmark_email.webhook_password', 'secret-pw')
        cls.env.company.email = 'info@example.com'
        cls.partner = cls.env['res.partner'].create({'name': 'Jane Client', 'email': 'jane@client.com'})
        cls.Log = cls.env['postmark.email.log']

    def _send_mail(self, **vals):
        """Send a mail.mail through the Postmark path; return the API payloads."""
        calls = []

        def fake_request(method, url, json=None, **kwargs):
            calls.append((method, url, json))
            return FakeResponse({'ErrorCode': 0, 'Message': 'OK', 'MessageID': 'pm-0001',
                                 'SubmittedAt': '2026-09-30T10:15:30.1234567Z'})

        mail = self.env['mail.mail'].create(dict({
            'subject': 'Your invoice',
            'body_html': '<p>Hello</p>',
            'email_from': 'Sales <sales@example.com>',
            'recipient_ids': [(4, self.partner.id)],
            'model': 'res.partner',
            'res_id': self.partner.id,
            'reply_to': 'catchall@example.com',
        }, **vals))
        with patch(REQUEST, side_effect=fake_request), \
                patch.object(type(self.env['ir.mail_server']), '_disable_send', return_value=False):
            mail.send(raise_exception=True)
        return mail, [c for c in calls if c[1].endswith('/email')]


@tagged('post_install', '-at_install')
class TestPostmarkSettings(PostmarkCase):

    def test_enabling_turns_off_other_mail_servers(self):
        settings = self.env['res.config.settings'].new({
            'external_email_server_default': True,
            'module_google_gmail': True,
            'module_microsoft_outlook': True,
        })
        settings.postmark_enabled = True
        settings._onchange_postmark_enabled()
        self.assertFalse(settings.external_email_server_default)
        self.assertFalse(settings.module_google_gmail)
        self.assertFalse(settings.module_microsoft_outlook)

    def test_parse_postmark_datetime(self):
        dt = postmark_api.parse_postmark_datetime('2014-02-17T07:25:01.4178645-05:00')
        self.assertEqual(dt.strftime('%d/%m/%Y %H:%M:%S'), '17/02/2014 12:25:01')


@tagged('post_install', '-at_install')
class TestPostmarkSend(PostmarkCase):

    def test_send_uses_api_and_logs(self):
        mail, calls = self._send_mail()
        self.assertEqual(len(calls), 1)
        method, url, payload = calls[0]
        self.assertEqual((method, url), ('POST', 'https://api.postmarkapp.com/email'))
        self.assertIn('jane@client.com', payload['To'])
        self.assertEqual(payload['Subject'], 'Your invoice')
        self.assertIn('Hello', payload['HtmlBody'])
        self.assertEqual(payload['Metadata']['odoo_model'], 'res.partner')
        self.assertEqual(payload['Metadata']['odoo_res_id'], str(self.partner.id))
        header_names = {h['Name'] for h in payload['Headers']}
        self.assertFalse({'X-Odoo-Postmark-Model', 'X-Odoo-Postmark-Res-Id'} & header_names)
        token = self.env['postmark.api']._record_token('res.partner', self.partner.id)
        self.assertEqual(payload['ReplyTo'], f'catchall+{token}@example.com')
        self.assertEqual(mail.state, 'sent')

        log = self.Log.search([('postmark_message_id', '=', 'pm-0001')])
        self.assertEqual(log.state, 'sent')
        self.assertEqual(log.direction, 'outgoing')
        self.assertEqual((log.res_model, log.res_id), ('res.partner', self.partner.id))
        self.assertEqual(log.date.strftime('%d/%m/%Y %H:%M'), '30/09/2026 10:15')

    def test_reply_rule_and_stream(self):
        stream = self.env['postmark.message.stream'].create({
            'name': 'Contacts', 'stream_id': 'contacts', 'stream_type': 'Transactional'})
        self.env['postmark.reply.rule'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'reply_to': 'contacts@example.com',
            'stream_id': stream.id,
        })
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.record_routing', False)
        __, calls = self._send_mail()
        payload = calls[0][2]
        self.assertEqual(payload['ReplyTo'], 'contacts@example.com')
        self.assertEqual(payload['MessageStream'], 'contacts')
        self.assertNotIn('Metadata', payload)

    def test_fallback_reply_to(self):
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.fallback_reply_to', 'hello@example.com')
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.record_routing', False)
        __, calls = self._send_mail()
        self.assertEqual(calls[0][2]['ReplyTo'], 'hello@example.com')

    def test_from_outside_sender_domain_is_rewritten(self):
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.from_filter', 'mycompany.com')
        self.env.company.alias_domain_id = self.env['mail.alias.domain'].create({
            'name': 'mycompany.com', 'default_from': 'notifications'})
        __, calls = self._send_mail(email_from='Sales Team <sales@gmail.com>')
        self.assertIn('notifications@mycompany.com', calls[0][2]['From'])
        self.assertIn('Sales Team', calls[0][2]['From'])

    def test_failed_send_is_logged(self):
        mail = self.env['mail.mail'].create({
            'subject': 'Fails', 'body_html': '<p>x</p>', 'email_from': 'sales@example.com',
            'email_to': 'jane@client.com',
        })
        with patch(REQUEST, return_value=FakeResponse(
                {'ErrorCode': 406, 'Message': 'Inactive recipient'}, status=422)), \
                patch.object(type(self.env['ir.mail_server']), '_disable_send', return_value=False), \
                mute_logger('odoo.addons.mail.models.mail_mail'):
            mail.send()
        self.assertEqual(mail.state, 'exception')
        log = self.Log.search([('subject', '=', 'Fails')])
        self.assertEqual(log.state, 'failed')
        self.assertIn('Inactive recipient', log.error)


@tagged('post_install', '-at_install')
class TestPostmarkInbound(PostmarkCase):

    def _inbound_payload(self, **vals):
        payload = {
            'From': 'jane@client.com',
            'FromName': 'Jane Client',
            'FromFull': {'Email': 'jane@client.com', 'Name': 'Jane Client', 'MailboxHash': ''},
            'To': 'catchall@example.com',
            'ToFull': [{'Email': 'catchall@example.com', 'Name': '', 'MailboxHash': ''}],
            'Subject': 'Re: Your invoice',
            'MessageID': 'in-0001',
            'MessageStream': 'inbound',
            'Date': 'Wed, 30 Sep 2026 11:00:00 +1000',
            'MailboxHash': '',
            'TextBody': 'Thanks, paid today.',
            'HtmlBody': '<p>Thanks, paid today.</p>',
            'Headers': [{'Name': 'Message-ID', 'Value': '<reply-0001@client.com>'}],
            'Attachments': [{
                'Name': 'receipt.txt', 'ContentType': 'text/plain',
                'Content': base64.b64encode(b'receipt').decode(), 'ContentID': '',
            }],
        }
        payload.update(vals)
        return payload

    def test_reply_token_logs_on_record(self):
        token = self.env['postmark.api']._record_token('res.partner', self.partner.id)
        log = self.Log._postmark_receive_inbound(self._inbound_payload(
            To=f'catchall+{token}@example.com', MailboxHash=token))
        self.assertEqual(log.state, 'received', log.error)
        self.assertEqual((log.res_model, log.res_id), ('res.partner', self.partner.id))
        message = self.env['mail.message'].search([('message_id', '=', '<reply-0001@client.com>')])
        self.assertEqual((message.model, message.res_id), ('res.partner', self.partner.id))
        self.assertIn('paid today', message.body)
        self.assertEqual(message.attachment_ids.name, 'receipt.txt')

    def test_forged_token_is_ignored(self):
        log = self.Log._postmark_receive_inbound(self._inbound_payload(
            MailboxHash=f'res.partner-{self.partner.id}-0000000000'))
        self.assertEqual(log.state, 'unrouted')
        self.assertFalse(log.res_id)

    def test_reply_matched_on_postmark_message_id(self):
        self._send_mail()
        log = self.Log._postmark_receive_inbound(self._inbound_payload(
            Headers=[{'Name': 'Message-ID', 'Value': '<reply-0002@client.com>'},
                     {'Name': 'In-Reply-To', 'Value': '<pm-0001@mtasv.net>'}]))
        self.assertEqual(log.state, 'received', log.error)
        self.assertEqual((log.res_model, log.res_id), ('res.partner', self.partner.id))

    def test_retry_unrouted(self):
        log = self.Log._postmark_receive_inbound(self._inbound_payload())
        self.assertEqual(log.state, 'unrouted')
        token = self.env['postmark.api']._record_token('res.partner', self.partner.id)
        log.payload = json.dumps(self._inbound_payload(MailboxHash=token))
        log.action_retry_inbound()
        self.assertEqual(log.state, 'received')


@tagged('post_install', '-at_install')
class TestPostmarkEvents(PostmarkCase):

    def _bounce(self, **vals):
        payload = {
            'RecordType': 'Bounce', 'ID': 42, 'Type': 'HardBounce', 'TypeCode': 1,
            'MessageID': 'pm-0001', 'Email': 'jane@client.com', 'From': 'sales@example.com',
            'BouncedAt': '2026-09-30T10:20:00Z', 'Inactive': True, 'Subject': 'Your invoice',
            'Description': 'The server was unable to deliver your message.',
            'Details': 'smtp;550 5.1.1 unknown user', 'MessageStream': 'outbound',
            'Metadata': {'odoo_model': 'res.partner', 'odoo_res_id': str(self.partner.id)},
        }
        payload.update(vals)
        return payload

    def test_hard_bounce_flags_log_partner_and_record(self):
        self._send_mail()
        log = self.Log._postmark_receive_event(self._bounce())
        self.assertEqual(log.state, 'bounced')
        self.assertEqual(log.event_type, 'HardBounce')
        self.assertEqual(self.partner.message_bounce, 1)
        self.assertIn('bounced', self.partner.message_ids[0].body)

    def test_soft_bounce_only_logged(self):
        self._send_mail()
        log = self.Log._postmark_receive_event(self._bounce(Type='SoftBounce', Inactive=False))
        self.assertEqual(log.state, 'soft_bounce')
        self.assertEqual(self.partner.message_bounce, 0)

    def test_spam_complaint_blacklists(self):
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.blacklist_spam', True)
        log = self.Log._postmark_receive_event(self._bounce(
            RecordType='SpamComplaint', Type='SpamComplaint', MessageID='pm-unknown'))
        self.assertEqual(log.state, 'spam')
        self.assertEqual((log.res_model, log.res_id), ('res.partner', self.partner.id))
        self.assertTrue(self.env['mail.blacklist'].search([('email', '=', 'jane@client.com')]))
        self.assertIn('spam', self.partner.message_ids[0].body)

    def test_delivery(self):
        self._send_mail()
        log = self.Log._postmark_receive_event({
            'RecordType': 'Delivery', 'MessageID': 'pm-0001', 'Recipient': 'jane@client.com',
            'DeliveredAt': '2026-09-30T10:16:00Z', 'Details': 'Test delivery'})
        self.assertEqual(log.state, 'delivered')


@tagged('post_install', '-at_install')
class TestPostmarkAliases(PostmarkCase):

    def test_alias_creates_reply_rule(self):
        self.env['ir.config_parameter'].sudo().set_param('postmark_email.alias_streams', True)
        domain = self.env['mail.alias.domain'].create({'name': 'example.org'})
        alias = self.env['mail.alias'].create({
            'alias_name': 'contacts', 'alias_domain_id': domain.id,
            'alias_model_id': self.env['ir.model']._get_id('res.partner'),
        })
        rule = self.env['postmark.reply.rule'].search([('alias_id', '=', alias.id)])
        self.assertEqual(rule.reply_to, 'contacts@example.org')
        self.assertEqual(rule.model, 'res.partner')
        alias.alias_name = 'people'
        self.assertEqual(rule.reply_to, 'people@example.org')
        alias.unlink()
        self.assertFalse(rule.active)

    def test_stream_id_for_alias(self):
        alias = self.env['mail.alias'].new({'alias_name': 'Accounts Payable & Receivable Team!!'})
        stream_id = self.env['postmark.message.stream']._postmark_stream_id_for_alias(alias)
        self.assertEqual(stream_id, 'odoo-accounts-payable-receivab')


@tagged('post_install', '-at_install')
class TestPostmarkSync(PostmarkCase):

    def test_sync_with_postmark(self):
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://odoo.example.com')
        calls = []

        def fake_request(method, url, json=None, params=None, **kwargs):
            path = url.removeprefix('https://api.postmarkapp.com')
            calls.append((method, path, json))
            if (method, path) == ('GET', '/server'):
                return FakeResponse({'ID': 1, 'Name': 'Odoo'})
            if (method, path) == ('GET', '/message-streams'):
                return FakeResponse({'TotalCount': 3, 'MessageStreams': [
                    {'ID': 'outbound', 'Name': 'Transactional', 'MessageStreamType': 'Transactional'},
                    {'ID': 'inbound', 'Name': 'Inbound', 'MessageStreamType': 'Inbound'},
                    {'ID': 'broadcast', 'Name': 'Newsletters', 'MessageStreamType': 'Broadcasts'},
                ]})
            if (method, path) == ('GET', '/webhooks'):
                return FakeResponse({'Webhooks': []})
            if (method, path) == ('POST', '/webhooks'):
                return FakeResponse({'ID': 100 + len(calls)})
            return FakeResponse({})

        settings = self.env['res.config.settings'].create({})
        with patch(REQUEST, side_effect=fake_request), \
                patch.object(type(self.env['ir.mail_server']), '_disable_send', return_value=False):
            action = settings.action_postmark_sync()
        self.assertEqual(action['params']['type'], 'success')
        Stream = self.env['postmark.message.stream']
        self.assertEqual(Stream.search([('stream_id', '=', 'broadcast')]).stream_type, 'Broadcasts')
        self.assertEqual(Stream.search([('stream_id', '=', 'outbound')]).name, 'Transactional')
        server_put = next(c for c in calls if c[:2] == ('PUT', '/server'))
        self.assertEqual(server_put[2]['InboundHookUrl'],
                         'https://postmark:secret-pw@odoo.example.com/postmark/webhook/inbound')
        webhooks = [c for c in calls if c[:2] == ('POST', '/webhooks')]
        self.assertEqual({c[2]['MessageStream'] for c in webhooks}, {'outbound', 'broadcast'})
        self.assertEqual(webhooks[0][2]['Url'], 'https://odoo.example.com/postmark/webhook/events')
        self.assertEqual(webhooks[0][2]['HttpAuth'], {'Username': 'postmark', 'Password': 'secret-pw'})
        self.assertTrue(webhooks[0][2]['Triggers']['SpamComplaint']['Enabled'])
        self.assertTrue(Stream.search([('stream_id', '=', 'outbound')]).webhook_id)

    def test_new_stream_is_created_in_postmark(self):
        calls = []

        def fake_request(method, url, json=None, params=None, **kwargs):
            calls.append((method, url.removeprefix('https://api.postmarkapp.com'), json))
            if method == 'GET':
                return FakeResponse({'Webhooks': []})
            return FakeResponse({'ID': 7})

        with patch(REQUEST, side_effect=fake_request), \
                patch.object(type(self.env['ir.mail_server']), '_disable_send', return_value=False):
            self.env['postmark.message.stream'].create({
                'name': 'Invoices', 'stream_id': 'invoices', 'stream_type': 'Transactional'})
        self.assertEqual(calls[0][:2], ('POST', '/message-streams'))
        self.assertEqual(calls[0][2]['ID'], 'invoices')


@tagged('post_install', '-at_install')
class TestPostmarkWebhooks(HttpCase):

    def setUp(self):
        super().setUp()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('postmark_email.enabled', True)
        ICP.set_param('postmark_email.webhook_user', 'postmark')
        ICP.set_param('postmark_email.webhook_password', 'secret-pw')

    def _post(self, path, payload, password='secret-pw'):
        auth = base64.b64encode(f'postmark:{password}'.encode()).decode()
        return self.url_open(path, data=json.dumps(payload),
                             headers={'Content-Type': 'application/json',
                                      'Authorization': f'Basic {auth}'})

    def test_requires_basic_auth(self):
        response = self._post('/postmark/webhook/events', {'RecordType': 'Delivery'}, password='wrong')
        self.assertEqual(response.status_code, 401)

    def test_inbound_webhook(self):
        partner = self.env['res.partner'].create({'name': 'Web Client', 'email': 'web@client.com'})
        token = self.env['postmark.api']._record_token('res.partner', partner.id)
        response = self._post('/postmark/webhook/inbound', {
            'From': 'web@client.com', 'FromFull': {'Email': 'web@client.com', 'Name': 'Web Client'},
            'To': f'catchall+{token}@example.com', 'Subject': 'Hi', 'MessageID': 'in-web',
            'MailboxHash': token, 'TextBody': 'Hello from the web',
            'Headers': [{'Name': 'Message-ID', 'Value': '<web-0001@client.com>'}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'received')
        self.assertIn('Hello from the web', partner.message_ids[0].body)

    def test_bounce_webhook(self):
        response = self._post('/postmark/webhook/events', {
            'RecordType': 'Bounce', 'Type': 'HardBounce', 'MessageID': 'pm-web',
            'Email': 'nobody@client.com', 'Inactive': True, 'Subject': 'Hello',
            'BouncedAt': '2026-09-30T10:20:00Z'})
        self.assertEqual(response.status_code, 200)
        log = self.env['postmark.email.log'].search([('postmark_message_id', '=', 'pm-web')])
        self.assertEqual(log.state, 'bounced')

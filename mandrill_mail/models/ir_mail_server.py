import email.policy
import json
import logging

from odoo import _, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.tools import email_normalize
from odoo.tools.mail import encapsulate_email

from .mandrill_api import MandrillError

_logger = logging.getLogger(__name__)

# Headers mail.mail adds (see mail_mail.py) to tell send_email which record
# an email comes from. They are removed before the email leaves Odoo.
HEADER_MODEL = 'X-Odoo-Mandrill-Model'
HEADER_RES_ID = 'X-Odoo-Mandrill-Res-Id'
HEADER_MESSAGE = 'X-Odoo-Mandrill-Message'
HEADER_TOKEN = 'X-Odoo-Mandrill-Token'
HEADER_RECORD_NAME = 'X-Odoo-Mandrill-Record'
INTERNAL_HEADERS = (HEADER_MODEL, HEADER_RES_ID, HEADER_MESSAGE, HEADER_TOKEN, HEADER_RECORD_NAME)

# Mandrill send statuses that mean the email was accepted.
ACCEPTED_STATUSES = ('sent', 'queued', 'scheduled')


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def _connect__(self, *args, **kwargs):  # noqa: PLW3201
        # Mail is sent over HTTPS, so there is no SMTP session to open. The
        # "Test Connection" button on an SMTP server still really connects.
        if self.env['mandrill.service']._is_enabled() and not self.env.context.get('mandrill_allow_smtp'):
            return None
        return super()._connect__(*args, **kwargs)

    def test_smtp_connection(self, autodetect_max_email_size=False):
        return super(IrMailServer, self.with_context(mandrill_allow_smtp=True)).test_smtp_connection(
            autodetect_max_email_size=autodetect_max_email_size)

    def send_email(self, message, mail_server_id=None, smtp_server=None, smtp_port=None,
                   smtp_user=None, smtp_password=None, smtp_encryption=None,
                   smtp_ssl_certificate=None, smtp_ssl_private_key=None,
                   smtp_debug=False, smtp_session=None):
        if self.env['mandrill.service']._is_enabled():
            return self._mandrill_send_email(message)
        for header in INTERNAL_HEADERS:
            del message[header]
        return super().send_email(
            message, mail_server_id=mail_server_id, smtp_server=smtp_server, smtp_port=smtp_port,
            smtp_user=smtp_user, smtp_password=smtp_password, smtp_encryption=smtp_encryption,
            smtp_ssl_certificate=smtp_ssl_certificate, smtp_ssl_private_key=smtp_ssl_private_key,
            smtp_debug=smtp_debug, smtp_session=smtp_session)

    def _mandrill_send_email(self, message):
        """Send ``message`` with Mandrill's ``messages/send-raw`` API.

        The MIME message Odoo built is sent as is, so Message-Id, References,
        attachments and inline images are untouched and replies thread
        normally. Mirrors core ``send_email``: returns the Message-Id or raises
        MailDeliveryException.
        """
        service = self.env['mandrill.service']
        context_info = {header: message[header] for header in INTERNAL_HEADERS}
        for header in INTERNAL_HEADERS:
            del message[header]

        self._mandrill_fix_from(message, service)
        if not message['From']:
            raise AssertionError(self.NO_FOUND_FROM)
        recipients = self._prepare_smtp_to_list(message, None)
        if not recipients:
            raise AssertionError(self.NO_VALID_RECIPIENT)
        # applies X-Forge-To & co. and drops Bcc (recipients are sent separately)
        self._alter_message__(message, message['From'], recipients)

        res_model = context_info[HEADER_MODEL] or False
        res_id = int(context_info[HEADER_RES_ID] or 0)
        self._mandrill_add_headers(message, service, res_model, res_id, context_info)

        message_id = message['Message-Id']
        log_vals = {
            'direction': 'outbound',
            'subject': str(message['Subject'] or ''),
            'email_from': str(message['From'] or ''),
            'email_to': str(message['To'] or ''),
            'email_cc': str(message['Cc'] or ''),
            'reply_to': str(message['Reply-To'] or ''),
            'message_id': message_id,
            'references': str(message['References'] or ''),
            'res_model': res_model,
            'res_id': res_id,
            'mail_message_id': int(context_info[HEADER_MESSAGE] or 0) or False,
            'reply_token': context_info[HEADER_TOKEN] or False,
            'metadata': str(message['X-MC-Metadata'] or '') or False,
        }

        if self._disable_send():
            _logger.debug("skip sending email via Mailchimp Transactional in test mode")
            return message_id

        Log = self.env['mandrill.mail.log'].sudo()
        try:
            results = service._get_api().send_raw(
                message.as_string(policy=email.policy.SMTP),
                to=[{'email': address} for address in recipients],
            ) or []
        except MandrillError as e:
            Log.create([dict(log_vals, recipient=address, state='error', error_message=str(e))
                        for address in recipients])
            msg = _("Mail delivery failed via Mailchimp Transactional.\n%s", e)
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg) from e

        Log.create([
            dict(
                log_vals,
                recipient=result.get('email'),
                mandrill_id=result.get('_id'),
                state=result.get('status') if result.get('status') in dict(Log._fields['state'].selection) else 'error',
                error_message=result.get('reject_reason') or False,
            )
            for result in results
        ])
        if results and not any(r.get('status') in ACCEPTED_STATUSES for r in results):
            reasons = ', '.join(f"{r.get('email')}: {r.get('reject_reason') or r.get('status')}" for r in results)
            msg = _("Mailchimp Transactional did not accept the email (%s).", reasons)
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)
        return message_id

    def _mandrill_fix_from(self, message, service):
        """Mandrill only sends from verified sending domains. When the From
        address is outside them, send from the notifications address instead
        and keep the author's name, as Odoo does for SMTP from filters."""
        from_filter = (service._get_param('sending_domains') or '').strip()
        email_from = message['From']
        if not from_filter or not email_from or self._match_from_filter(email_from, from_filter):
            return
        notifications_email = email_normalize(
            self.env.context.get('domain_notifications_email') or self._get_default_from_address() or '')
        if notifications_email:
            message.replace_header('From', encapsulate_email(email_from, notifications_email))

    def _mandrill_add_headers(self, message, service, res_model, res_id, context_info):
        """Mandrill's X-MC-* headers: tracking, subaccount and the record
        details sent as metadata (see "Include Record Details")."""
        track = [name for name, key in (('opens', 'track_opens'), ('clicks_all', 'track_clicks'))
                 if service._get_param(key)]
        if track:
            message['X-MC-Track'] = ','.join(track)
        subaccount = (service._get_param('subaccount') or '').strip()
        if subaccount:
            message['X-MC-Subaccount'] = subaccount
        if service._get_param('reply_tracking') and res_model and res_id:
            metadata = {
                'odoo_db': self.env.cr.dbname,
                'odoo_model': res_model,
                'odoo_res_id': str(res_id),
            }
            if context_info[HEADER_RECORD_NAME]:
                metadata['odoo_record'] = str(context_info[HEADER_RECORD_NAME])[:200]
            if context_info[HEADER_TOKEN]:
                metadata['odoo_ref'] = str(context_info[HEADER_TOKEN])
            message['X-MC-Metadata'] = json.dumps(metadata)
            message['X-MC-Tags'] = res_model.replace('.', '-')

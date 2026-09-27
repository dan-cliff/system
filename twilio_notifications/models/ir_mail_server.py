import base64
import html
import logging
from email.header import decode_header, make_header
from email.utils import getaddresses

import requests

from odoo import _, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)

TWILIO_EMAIL_SEND_URL = 'https://comms.twilio.com/v1/Emails'
TWILIO_REQUEST_TIMEOUT = 15


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def send_email(self, message, mail_server_id=None, smtp_server=None, smtp_port=None,
                    smtp_user=None, smtp_password=None, smtp_encryption=None,
                    smtp_ssl_certificate=None, smtp_ssl_private_key=None,
                    smtp_debug=False, smtp_session=None):
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('twilio_notifications.enabled'):
            return self._twilio_send_email(message)
        return super().send_email(
            message, mail_server_id=mail_server_id, smtp_server=smtp_server, smtp_port=smtp_port,
            smtp_user=smtp_user, smtp_password=smtp_password, smtp_encryption=smtp_encryption,
            smtp_ssl_certificate=smtp_ssl_certificate, smtp_ssl_private_key=smtp_ssl_private_key,
            smtp_debug=smtp_debug, smtp_session=smtp_session)

    def _twilio_send_email(self, message):
        """Send ``message`` via the Twilio Email API instead of SMTP.

        Mirrors the contract of the core ``send_email``: returns the
        Message-Id on success, raises MailDeliveryException on failure.
        """
        message_id = message['Message-Id']

        if self._disable_send():
            _logger.debug("skip sending email via Twilio Email API in test mode")
            return message_id

        ICP = self.env['ir.config_parameter'].sudo()
        sid = (ICP.get_param('twilio_notifications.sid') or '').strip()
        secret = (ICP.get_param('twilio_notifications.secret') or '').strip()
        from_email = (ICP.get_param('twilio_notifications.from_email') or '').strip()
        from_name = (ICP.get_param('twilio_notifications.from_name') or '').strip()

        if not (sid and secret and from_email):
            msg = _(
                "Twilio email notifications are enabled but the Twilio SID, Secret and From "
                "Email are not fully configured in Settings > General Settings > Emails."
            )
            _logger.error(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)

        to_addresses = self._twilio_get_addresses(message, 'To')
        cc_addresses = self._twilio_get_addresses(message, 'Cc')
        bcc_addresses = self._twilio_get_addresses(message, 'Bcc')
        if not (to_addresses or cc_addresses or bcc_addresses):
            msg = _("No recipient address found on the outgoing message.")
            _logger.error(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)
        if not to_addresses:
            # The Twilio Email API requires a "to" entry; fall back to whichever
            # recipients are available so Cc/Bcc-only messages still go out.
            to_addresses, cc_addresses, bcc_addresses = (cc_addresses or bcc_addresses), [], []

        text_body, html_body, attachments = self._twilio_extract_content(message)
        if not html_body:
            html_body = '<pre>%s</pre>' % html.escape(text_body or '')

        payload = {
            'from': {'address': from_email, 'name': from_name} if from_name else {'address': from_email},
            'to': [{'address': address} for address in to_addresses],
            'content': {
                'subject': self._twilio_decode_header(message['Subject']),
                'html': html_body,
            },
        }
        if cc_addresses:
            payload['cc'] = [{'address': address} for address in cc_addresses]
        if bcc_addresses:
            payload['bcc'] = [{'address': address} for address in bcc_addresses]
        if text_body:
            payload['content']['text'] = text_body
        if attachments:
            payload['content']['attachments'] = attachments

        try:
            response = requests.post(
                TWILIO_EMAIL_SEND_URL, json=payload, auth=(sid, secret), timeout=TWILIO_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            detail = e.response.text if getattr(e, 'response', None) is not None else str(e)
            msg = _(
                "Mail delivery failed via the Twilio Email API.\n%(exception_name)s: %(message)s",
                exception_name=e.__class__.__name__,
                message=detail,
            )
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)

        return message_id

    @staticmethod
    def _twilio_decode_header(value):
        if not value:
            return ''
        return str(make_header(decode_header(value)))

    @staticmethod
    def _twilio_get_addresses(message, header):
        return [address for _name, address in getaddresses(message.get_all(header, [])) if address]

    @staticmethod
    def _twilio_extract_content(message):
        """Split ``message`` into its text/html bodies and its attachments.

        A part is treated as an attachment (rather than a body part) when it
        carries a filename or an explicit ``Content-Disposition: attachment``,
        matching how Odoo's own MIME builder marks ir.attachment records on
        outgoing mail. Everything else is folded into the plain-text/HTML
        body, same as core send_email's SMTP path sees it.
        """
        text_body = None
        html_body = None
        attachments = []
        parts = message.walk() if message.is_multipart() else [message]
        for part in parts:
            if part.is_multipart():
                continue

            filename = part.get_filename()
            is_attachment = part.get_content_disposition() == 'attachment' or bool(filename)
            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            if is_attachment:
                attachment = {
                    'filename': filename or 'attachment',
                    'contentType': part.get_content_type(),
                    'content': base64.b64encode(payload).decode('ascii'),
                }
                content_id = part.get('Content-ID')
                if content_id:
                    attachment['cid'] = content_id.strip('<>')
                attachments.append(attachment)
                continue

            content_type = part.get_content_type()
            if content_type not in ('text/plain', 'text/html'):
                continue
            charset = part.get_content_charset() or 'utf-8'
            try:
                content = payload.decode(charset, errors='replace')
            except LookupError:
                content = payload.decode('utf-8', errors='replace')
            if content_type == 'text/html' and html_body is None:
                html_body = content
            elif content_type == 'text/plain' and text_body is None:
                text_body = content
        return text_body, html_body, attachments

import base64
import logging
from email.header import decode_header, make_header
from email.utils import formataddr, getaddresses, parseaddr

from odoo import _, api, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.tools.mail import email_normalize

from .postmark_api import (
    PARAM_DEFAULT_STREAM, PARAM_FALLBACK_REPLY_TO, PARAM_FROM_FILTER, PARAM_RECORD_ROUTING,
    PostmarkError, parse_postmark_datetime,
)

_logger = logging.getLogger(__name__)

# Set by mail.mail on outgoing emails so the send knows which record it came
# from; always removed before the email leaves Odoo.
HEADER_MODEL = 'X-Odoo-Postmark-Model'
HEADER_RES_ID = 'X-Odoo-Postmark-Res-Id'
HEADER_MAIL_MESSAGE = 'X-Odoo-Postmark-Message'
ODOO_HEADERS = (HEADER_MODEL, HEADER_RES_ID, HEADER_MAIL_MESSAGE)

# Headers Postmark builds from its own JSON fields (or from the body/attachments).
POSTMARK_SKIP_HEADERS = {
    'from', 'to', 'cc', 'bcc', 'subject', 'reply-to', 'date', 'return-path',
    'mime-version', 'content-type', 'content-transfer-encoding',
}


class PostmarkSession:
    """Stands in for the SMTP session mail.mail opens before sending.

    Emails go out over the Postmark HTTP API, so there is nothing to connect
    to; ``from_filter`` / ``smtp_from`` feed Odoo's own From rewriting.
    """

    def __init__(self, from_filter=False, smtp_from=False):
        self.from_filter = from_filter
        self.smtp_from = smtp_from

    def quit(self):
        pass


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def _connect__(self, *args, **kwargs):  # noqa: PLW3201
        if self.env['postmark.api']._is_enabled() and not self._disable_send():
            return PostmarkSession()
        return super()._connect__(*args, **kwargs)

    @api.model
    def send_email(self, message, mail_server_id=None, smtp_server=None, smtp_port=None,
                   smtp_user=None, smtp_password=None, smtp_encryption=None,
                   smtp_ssl_certificate=None, smtp_ssl_private_key=None,
                   smtp_debug=False, smtp_session=None):
        if self.env['postmark.api']._is_enabled():
            return self._postmark_send_email(message)
        for header in ODOO_HEADERS:
            del message[header]
        return super().send_email(
            message, mail_server_id=mail_server_id, smtp_server=smtp_server, smtp_port=smtp_port,
            smtp_user=smtp_user, smtp_password=smtp_password, smtp_encryption=smtp_encryption,
            smtp_ssl_certificate=smtp_ssl_certificate, smtp_ssl_private_key=smtp_ssl_private_key,
            smtp_debug=smtp_debug, smtp_session=smtp_session)

    def _postmark_send_email(self, message):
        """Send ``message`` through the Postmark Email API instead of SMTP.

        Keeps the contract of the core ``send_email``: returns the Message-Id
        on success, raises MailDeliveryException on failure, and an
        AssertionError(NO_VALID_RECIPIENT) when there is nobody to send to.
        """
        model = message[HEADER_MODEL] or False
        res_id = int(message[HEADER_RES_ID]) if (message[HEADER_RES_ID] or '').isdigit() else False
        mail_message_id = int(message[HEADER_MAIL_MESSAGE]) if (message[HEADER_MAIL_MESSAGE] or '').isdigit() else False
        for header in ODOO_HEADERS:
            del message[header]

        message_id = message['Message-Id']
        if self._disable_send():
            _logger.debug("skip sending email via Postmark in test mode")
            return message_id

        Api = self.env['postmark.api']
        payload, stream = self._postmark_prepare_payload(message, model, res_id, mail_message_id)
        log_vals = {
            'direction': 'outgoing',
            'subject': payload['Subject'],
            'email_from': payload['From'],
            'email_to': payload.get('To'),
            'email_cc': payload.get('Cc'),
            'email_bcc': payload.get('Bcc'),
            'reply_to': payload.get('ReplyTo'),
            'stream_id': stream.id,
            'message_id': message_id,
            'res_model': model if res_id else False,
            'res_id': res_id,
            'mail_message_id': mail_message_id or False,
        }
        Log = self.env['postmark.email.log'].sudo()
        try:
            response = Api._request('POST', '/email', payload)
        except PostmarkError as e:
            Log.create(dict(log_vals, state='failed', error=e.message))
            msg = _("Mail delivery failed via Postmark.\n%s", e.message)
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg) from e

        log_vals.update(state='sent', postmark_message_id=response.get('MessageID'))
        if submitted_at := parse_postmark_datetime(response.get('SubmittedAt')):
            log_vals['date'] = submitted_at
        Log.create(log_vals)
        return message_id

    # ------------------------------------------------------------------
    # Building the Postmark payload
    # ------------------------------------------------------------------

    def _postmark_prepare_payload(self, message, model, res_id, mail_message_id):
        Api = self.env['postmark.api']
        bcc_header = message['Bcc']  # removed from the message by _prepare_email_message__

        # Postmark only sends from verified domains / sender signatures. Mirror
        # what Odoo does for an SMTP server's "FROM Filtering": outside the
        # allowed domains, send from the notifications address as
        # "Original Name" <notifications@...>.
        from_filter = Api._get_param(PARAM_FROM_FILTER)
        smtp_from = message['From']
        if from_filter and not self._match_from_filter(smtp_from, from_filter):
            notifications = (self.env.context.get('domain_notifications_email')
                             or self._get_default_from_address())
            if notifications:
                smtp_from = notifications
        session = PostmarkSession(from_filter=from_filter, smtp_from=smtp_from)
        __, smtp_to_list, message = self._prepare_email_message__(message, session)

        recipients = {email_normalize(a, strict=False) for a in smtp_to_list}
        to = self._postmark_filter_addresses(message.get_all('To', []), recipients)
        cc = self._postmark_filter_addresses(message.get_all('Cc', []), recipients)
        bcc = self._postmark_filter_addresses([bcc_header] if bcc_header else [], recipients)
        listed = {email_normalize(parseaddr(a)[1], strict=False) for a in to + cc + bcc}
        bcc += [a for a in smtp_to_list if email_normalize(a, strict=False) not in listed]
        if not to:
            # Postmark needs a To; keep Cc/Bcc-only emails going out.
            if cc:
                to, cc = cc, []
            else:
                to, bcc = bcc, []

        text_body, html_body, attachments = self._postmark_extract_content(message)
        reply_to, rule = self._postmark_reply_to(message['Reply-To'], model, res_id)
        stream = rule.stream_id if rule and rule.stream_id.active else self.env['postmark.message.stream']
        if not stream:
            stream = self.env['postmark.message.stream'].sudo().browse(
                int(Api._get_param(PARAM_DEFAULT_STREAM) or 0)).exists()

        payload = {
            'From': self._postmark_decode(message['From']),
            'To': ', '.join(to),
            'Subject': self._postmark_decode(message['Subject']),
            'Headers': [
                {'Name': name, 'Value': self._postmark_decode(value)}
                for name, value in message.items()
                if name.lower() not in POSTMARK_SKIP_HEADERS
            ],
        }
        if cc:
            payload['Cc'] = ', '.join(cc)
        if bcc:
            payload['Bcc'] = ', '.join(bcc)
        if reply_to:
            payload['ReplyTo'] = reply_to
        if html_body:
            payload['HtmlBody'] = html_body
        if text_body or not html_body:
            payload['TextBody'] = text_body or ''
        if attachments:
            payload['Attachments'] = attachments
        if stream:
            payload['MessageStream'] = stream.stream_id
        if Api._get_param(PARAM_RECORD_ROUTING) and model and res_id:
            # Returned by Postmark with bounce / spam complaint webhooks.
            payload['Metadata'] = {'odoo_model': model, 'odoo_res_id': str(res_id)}
            if mail_message_id:
                payload['Metadata']['odoo_message'] = str(mail_message_id)
        return payload, stream

    def _postmark_reply_to(self, current_reply_to, model, res_id):
        """Return ``(reply_to, rule)`` for an email sent from ``model``.

        The model's reply address (Postmark Reply Addresses) wins, else the
        fallback reply-to from Settings, else the reply-to Odoo chose. With
        "Link Replies to Records" on, a token naming the record is added as a
        plus address so the reply can be logged on it.
        """
        Api = self.env['postmark.api']
        current_reply_to = self._postmark_decode(current_reply_to) if current_reply_to else ''
        current_name, current_email = parseaddr(current_reply_to)
        rule = self.env['postmark.reply.rule']._postmark_find(model, current_email)
        address = rule.reply_to if rule else (Api._get_param(PARAM_FALLBACK_REPLY_TO) or current_email)
        address = (address or '').strip()
        if not address:
            return current_reply_to, rule
        if Api._get_param(PARAM_RECORD_ROUTING) and model and res_id and '@' in address:
            local, domain = address.rsplit('@', 1)
            token = Api._record_token(model, res_id)
            local = local.split('+', 1)[0]
            if len(local) + len(token) + 1 <= 64:
                address = f'{local}+{token}@{domain}'
        return (formataddr((current_name, address)) if current_name else address), rule

    @staticmethod
    def _postmark_filter_addresses(headers, recipients):
        """Keep the formatted addresses from ``headers`` that are real recipients."""
        return [
            formataddr((name, addr)) if name else addr
            for name, addr in getaddresses([IrMailServer._postmark_decode(h) for h in headers])
            if addr and email_normalize(addr, strict=False) in recipients
        ]

    @staticmethod
    def _postmark_decode(value):
        if not value:
            return ''
        return str(make_header(decode_header(str(value))))

    @staticmethod
    def _postmark_extract_content(message):
        """Split ``message`` into its text/html bodies and its attachments.

        A part is an attachment when it has a filename or an explicit
        ``Content-Disposition: attachment``, as Odoo marks ir.attachment
        records on outgoing mail. Inline images keep their Content-ID so
        ``cid:`` links in the HTML body still resolve.
        """
        text_body = None
        html_body = None
        attachments = []
        for part in (message.walk() if message.is_multipart() else [message]):
            if part.is_multipart():
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            if part.get_content_disposition() == 'attachment' or filename:
                attachment = {
                    'Name': filename or 'attachment',
                    'Content': base64.b64encode(payload).decode('ascii'),
                    'ContentType': part.get_content_type(),
                }
                if content_id := (part.get('Content-ID') or '').strip('<> '):
                    attachment['ContentID'] = f'cid:{content_id}'
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

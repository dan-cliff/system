import secrets

from odoo import models
from odoo.tools import formataddr, parse_contact_from_email

from .ir_mail_server import HEADER_MESSAGE, HEADER_MODEL, HEADER_RECORD_NAME, HEADER_RES_ID, HEADER_TOKEN


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def _prepare_outgoing_list(self, mail_server=False, doc_to_followers=None):
        """Apply the per-model reply-to address and reply tracking, and tell
        ``ir.mail_server.send_email`` which record the email comes from."""
        email_list = super()._prepare_outgoing_list(mail_server=mail_server, doc_to_followers=doc_to_followers)
        service = self.env['mandrill.service']
        if not service._is_enabled():
            return email_list

        model, res_id = self.model, self.res_id
        company = self.mail_message_id.record_company_id or self.env.company
        reply_to = service._get_reply_to(model, company=company)
        token = secrets.token_hex(6) if model and res_id and service._reply_tracking_enabled() else False
        record_name = self.record_name or ''

        for email_values in email_list:
            if reply_to:
                email_values['reply_to'] = self._mandrill_format_reply_to(reply_to, email_values.get('reply_to'))
            if token and email_values.get('reply_to'):
                email_values['reply_to'] = service._add_reply_token(email_values['reply_to'], token)
            headers = dict(email_values.get('headers') or {})
            if model:
                headers[HEADER_MODEL] = model
            if res_id:
                headers[HEADER_RES_ID] = str(res_id)
            if self.mail_message_id:
                headers[HEADER_MESSAGE] = str(self.mail_message_id.id)
            if token:
                headers[HEADER_TOKEN] = token
            if record_name:
                headers[HEADER_RECORD_NAME] = record_name
            email_values['headers'] = headers
        return email_list

    @staticmethod
    def _mandrill_format_reply_to(reply_to, original):
        """Use ``reply_to``, keeping the display name Odoo gave the original
        reply-to (e.g. "Company - Invoice INV/0001") when it has none."""
        if original and '<' not in reply_to and ',' not in reply_to:
            name, _email = parse_contact_from_email(original)
            if name:
                return formataddr((name, reply_to.strip()))
        return reply_to

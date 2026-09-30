from odoo import models

from .ir_mail_server import HEADER_MAIL_MESSAGE, HEADER_MODEL, HEADER_RES_ID


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def _prepare_outgoing_list(self, mail_server=False, doc_to_followers=None):
        """Tell the Postmark send which record and message each email is for."""
        results = super()._prepare_outgoing_list(mail_server=mail_server, doc_to_followers=doc_to_followers)
        if not self.env['postmark.api']._is_enabled():
            return results
        extra = {HEADER_MAIL_MESSAGE: str(self.mail_message_id.id)}
        if self.model and self.res_id:
            extra.update({HEADER_MODEL: self.model, HEADER_RES_ID: str(self.res_id)})
        for email_values in results:
            email_values['headers'] = dict(email_values.get('headers') or {}, **extra)
        return results

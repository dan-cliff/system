from odoo import api, fields, models
from odoo.tools.mail import email_normalize


class PostmarkReplyRule(models.Model):
    _name = 'postmark.reply.rule'
    _description = 'Postmark Reply Address'
    _order = 'sequence, id'
    _rec_name = 'reply_to'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        domain=[('is_mail_thread', '=', True)],
        help="Emails sent from records of this model use this reply-to address.")
    model = fields.Char(string='Model Name', related='model_id.model', store=True, index=True)
    reply_to = fields.Char(
        string='Reply-To Email', required=True,
        help="Address replies are sent to, e.g. invoices@mycompany.com.")
    stream_id = fields.Many2one(
        'postmark.message.stream', string='Message Stream', ondelete='set null',
        domain=[('stream_type', '!=', 'Inbound')],
        help="Postmark stream the emails are sent through. Leave empty to use "
             "the default message stream.")
    alias_id = fields.Many2one(
        'mail.alias', string='Alias', ondelete='set null', readonly=True,
        help="The Odoo alias this reply address was created from.")

    @api.model
    def _postmark_find(self, model, current_reply_to=False):
        """Return the rule to use for an email sent from a ``model`` record.

        When a model has several rules (e.g. one per helpdesk team alias), the
        one matching the reply-to Odoo already chose for the record wins, else
        the first by sequence.
        """
        if not model:
            return self.browse()
        rules = self.sudo().search([('model', '=', model)])
        if len(rules) > 1 and current_reply_to:
            current = email_normalize(current_reply_to)
            matching = rules.filtered(lambda r: email_normalize(r.reply_to) == current)
            if matching:
                return matching[:1]
        return rules[:1]

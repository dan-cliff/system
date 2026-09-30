from odoo import api, models

from .postmark_api import PARAM_ALIAS_STREAMS

ALIAS_SYNC_FIELDS = {'alias_name', 'alias_domain_id', 'alias_model_id'}


class MailAlias(models.Model):
    _inherit = 'mail.alias'

    @api.model_create_multi
    def create(self, vals_list):
        aliases = super().create(vals_list)
        aliases._postmark_sync_aliases()
        return aliases

    def write(self, vals):
        res = super().write(vals)
        if ALIAS_SYNC_FIELDS & set(vals):
            self._postmark_sync_aliases()
        return res

    def unlink(self):
        if self.ids:
            self.env['postmark.reply.rule'].sudo().search(
                [('alias_id', 'in', self.ids)]).write({'active': False})
        return super().unlink()

    def _postmark_sync_aliases(self):
        """Give each named alias a reply address and a Postmark message stream.

        Emails sent from the alias's model then reply to the alias and go out
        through the alias's stream (see "Create Message Streams from Aliases"
        in Settings).
        """
        Api = self.env['postmark.api']
        if not (Api._is_enabled() and Api._get_param(PARAM_ALIAS_STREAMS)):
            return
        Rule = self.env['postmark.reply.rule'].sudo().with_context(active_test=False)
        Stream = self.env['postmark.message.stream'].sudo()
        push = Api._is_configured() and not Api._calls_disabled()
        for alias in self.sudo():
            rule = Rule.search([('alias_id', '=', alias.id)], limit=1)
            if not alias.alias_name or '@' not in (alias.alias_full_name or ''):
                rule.write({'active': False})
                continue
            vals = {
                'model_id': alias.alias_model_id.id,
                'reply_to': alias.alias_full_name,
                'active': True,
            }
            if push and not (rule.stream_id and rule.stream_id.alias_id == alias):
                vals['stream_id'] = Stream._postmark_ensure_alias_stream(alias).id or rule.stream_id.id
            elif push and rule.stream_id:
                Stream._postmark_ensure_alias_stream(alias)  # keep its name in step
            if rule:
                rule.write(vals)
            else:
                Rule.create(dict(vals, alias_id=alias.id))

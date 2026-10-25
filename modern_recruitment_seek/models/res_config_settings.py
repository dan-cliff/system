# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError

from .seek_api import SEEK_SCHEME

WEBHOOK_MUTATION = """
mutation TalentSeekWebhook($input: CreateWebhookSubscriptionInput!) {
  createWebhookSubscription(input: $input) {
    ... on CreateWebhookSubscriptionPayload_Success { webhookSubscription { id { value } } }
    ... on CreateWebhookSubscriptionPayload_Conflict { conflictingWebhookSubscription { id { value } } }
  }
}
"""


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    seek_client_id = fields.Char(related='company_id.seek_client_id', readonly=False)
    seek_client_secret = fields.Char(related='company_id.seek_client_secret', readonly=False)
    seek_hirer_id = fields.Char(related='company_id.seek_hirer_id', readonly=False)
    seek_webhook_subscription_id = fields.Char(related='company_id.seek_webhook_subscription_id')
    seek_webhook_url = fields.Char(string='SEEK Webhook Address', compute='_compute_seek_webhook_url')

    @api.depends('company_id')
    def _compute_seek_webhook_url(self):
        for settings in self:
            settings.seek_webhook_url = '%s/talent/seek/webhook/%s' % (
                settings.company_id.get_base_url(), settings.company_id.id)

    def _seek_notify(self, message):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'success'}}

    def action_seek_test(self):
        self.execute()  # save the credentials first
        self.env['talent.seek.api']._seek_token(self.company_id)
        return self._seek_notify(self.env._('Connected to SEEK.'))

    def action_seek_sync_categories(self):
        self.execute()
        count = self.env['talent.seek.category']._seek_sync(self.company_id)
        return self._seek_notify(self.env._('%s SEEK categories loaded.', count))

    def action_seek_register_webhook(self):
        """Ask SEEK to send new applications to this database."""
        self.execute()
        company = self.env['talent.seek.api']._seek_company(self.company_id)
        if not company.seek_webhook_secret:
            company.seek_webhook_secret = secrets.token_hex(32)
        if not self.seek_webhook_url.startswith('https://'):
            raise UserError(self.env._('SEEK only sends applications to an https:// address.'))
        data = self.env['talent.seek.api']._seek_query(WEBHOOK_MUTATION, {'input': {'webhookSubscription': {
            'eventTypeCode': 'CandidateApplicationCreated',
            'hirerId': company.seek_hirer_id,
            'schemeId': SEEK_SCHEME,
            'url': self.seek_webhook_url,
            'signingAlgorithmCode': 'SeekHmacSha512',
            'secret': company.seek_webhook_secret,
        }}}, company).get('createWebhookSubscription') or {}
        subscription = data.get('webhookSubscription') or data.get('conflictingWebhookSubscription') or {}
        company.seek_webhook_subscription_id = (subscription.get('id') or {}).get('value') or False
        return self._seek_notify(self.env._('SEEK will send new applications to Talent.'))

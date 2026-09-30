import secrets
from urllib.parse import quote, urlsplit, urlunsplit

from odoo import _, api, fields, models

from .postmark_api import (
    EVENTS_WEBHOOK_PATH, INBOUND_WEBHOOK_PATH, PARAM_ALIAS_STREAMS, PARAM_WEBHOOK_PASSWORD,
    PARAM_WEBHOOK_USER, PostmarkError,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    postmark_enabled = fields.Boolean(
        string='Postmark Email Service',
        config_parameter='postmark_email.enabled',
        help="Use postmark as your incoming and outgoing mail service. Turning this on "
             "turns off Use Custom Email Servers, Use an Outlook Server and Use a Gmail "
             "Server.")
    postmark_server_token = fields.Char(
        string='Server API Token',
        config_parameter='postmark_email.server_token',
        help="The API token of your Postmark server (Postmark > Servers > your server > "
             "API Tokens). Used to send emails and manage streams and webhooks.")
    postmark_from_filter = fields.Char(
        string='Sender Domains',
        config_parameter='postmark_email.from_filter',
        help="Domains (or addresses) verified as senders in Postmark, separated by commas. "
             "Emails from any other address are sent from the company's notifications "
             "address, showing the original sender's name. Leave empty to send every "
             "email from its own address.")
    postmark_default_stream_id = fields.Many2one(
        'postmark.message.stream', string='Default Message Stream',
        config_parameter='postmark_email.default_stream_id',
        domain=[('stream_type', '!=', 'Inbound')],
        help="Stream used for emails from models without their own reply address stream.")
    postmark_fallback_reply_to = fields.Char(
        string='Fallback Reply-To',
        config_parameter='postmark_email.fallback_reply_to',
        help="Reply-to address for emails from models without their own reply address. "
             "Leave empty to keep the reply-to Odoo chooses (usually the catchall).")
    postmark_record_routing = fields.Boolean(
        string='Link Replies to Records',
        config_parameter='postmark_email.record_routing',
        help="Adds the record an email was sent from to the email's Postmark metadata and "
             "its reply-to address (reply+<record>@...), so replies, bounces and spam "
             "complaints are logged on that record, e.g. a reply to an invoice email is "
             "logged on the invoice.")
    postmark_alias_streams = fields.Boolean(
        string='Create Message Streams from Aliases',
        config_parameter='postmark_email.alias_streams',
        help="Each email alias gets a reply address and its own Postmark message stream, "
             "created and renamed with the alias. Postmark allows 10 streams per server; "
             "aliases over the limit use the default stream.")
    postmark_blacklist_spam = fields.Boolean(
        string='Blacklist Spam Complaints',
        config_parameter='postmark_email.blacklist_spam',
        help="Add addresses that mark an email as spam to the email blacklist.")
    postmark_stream_count = fields.Integer(compute='_compute_postmark_counts')
    postmark_reply_rule_count = fields.Integer(compute='_compute_postmark_counts')
    postmark_inbound_url = fields.Char(string='Inbound Webhook URL', compute='_compute_postmark_urls')
    postmark_events_url = fields.Char(string='Bounce / Spam Webhook URL', compute='_compute_postmark_urls')

    def _compute_postmark_counts(self):
        streams = self.env['postmark.message.stream'].search_count([])
        rules = self.env['postmark.reply.rule'].search_count([])
        for settings in self:
            settings.postmark_stream_count = streams
            settings.postmark_reply_rule_count = rules

    def _compute_postmark_urls(self):
        base_url = self._postmark_base_url()
        for settings in self:
            settings.postmark_inbound_url = base_url + INBOUND_WEBHOOK_PATH
            settings.postmark_events_url = base_url + EVENTS_WEBHOOK_PATH

    @api.onchange('postmark_enabled')
    def _onchange_postmark_enabled(self):
        if self.postmark_enabled:
            self.external_email_server_default = False
            self.module_google_gmail = False
            self.module_microsoft_outlook = False

    def set_values(self):
        super().set_values()
        if self.postmark_enabled:
            self.env['ir.config_parameter'].sudo().set_param('base_setup.default_external_email_server', False)

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    @api.model
    def _postmark_base_url(self):
        return (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')

    @api.model
    def _postmark_webhook_credentials(self):
        """Basic auth username / password Postmark sends with each webhook."""
        ICP = self.env['ir.config_parameter'].sudo()
        user = ICP.get_param(PARAM_WEBHOOK_USER)
        password = ICP.get_param(PARAM_WEBHOOK_PASSWORD)
        if not (user and password):
            user, password = 'postmark', secrets.token_urlsafe(24)
            ICP.set_param(PARAM_WEBHOOK_USER, user)
            ICP.set_param(PARAM_WEBHOOK_PASSWORD, password)
        return user, password

    @api.model
    def _postmark_inbound_hook_url(self):
        user, password = self._postmark_webhook_credentials()
        parts = urlsplit(self._postmark_base_url() + INBOUND_WEBHOOK_PATH)
        netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_postmark_sync(self):
        """Check the token, pull the streams and point Postmark's webhooks at Odoo."""
        self.set_values()
        Api = self.env['postmark.api']
        Stream = self.env['postmark.message.stream'].sudo()
        try:
            server = Api._request('GET', '/server')
            Stream._postmark_sync_from_server()
            Api._request('PUT', '/server', {
                'InboundHookUrl': self._postmark_inbound_hook_url(),
                'RawEmailEnabled': True,
            })
            if Api._get_param(PARAM_ALIAS_STREAMS):
                self.env['mail.alias'].sudo().search([('alias_name', '!=', False)])._postmark_sync_aliases()
            for stream in Stream.search([('stream_type', '!=', 'Inbound')]):
                stream._postmark_configure_webhook()
        except PostmarkError as e:
            raise Api._user_error(e) from e
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Connected to Postmark"),
                'message': _("Server \"%s\": message streams synced and webhooks set up.",
                             server.get('Name') or ''),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _postmark_open(self, model, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_postmark_streams(self):
        return self._postmark_open('postmark.message.stream', _("Postmark Message Streams"))

    def action_postmark_reply_rules(self):
        return self._postmark_open('postmark.reply.rule', _("Postmark Reply Addresses"))

    def action_postmark_logs(self):
        return self._postmark_open('postmark.email.log', _("Postmark Email Log"))

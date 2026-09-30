from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mandrill_api import MandrillError
from .mandrill_service import EVENTS_PATH, INBOUND_PATH


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mandrill_enabled = fields.Boolean(
        string='Mailchimp Transactional Email Service',
        config_parameter='mandrill_mail.enabled',
        help='Use Mailchimp Transactional (formerly Mandrill) as your incoming and outgoing mail service.',
    )
    mandrill_api_key = fields.Char(
        string='API Key',
        config_parameter='mandrill_mail.api_key',
        help='Mailchimp Transactional API key (Mandrill > Settings > SMTP & API Info).',
    )
    mandrill_subaccount = fields.Char(
        string='Subaccount',
        config_parameter='mandrill_mail.subaccount',
        help='Optional Mailchimp Transactional subaccount ID to send from.',
    )
    mandrill_sending_domains = fields.Char(
        string='Sending Domains',
        config_parameter='mandrill_mail.sending_domains',
        help='Comma-separated domains verified in Mailchimp Transactional. Emails from any other '
             'address are sent from the notifications address, keeping the author\'s name. '
             'Leave empty to always send from the author\'s address.',
    )
    mandrill_default_reply_to = fields.Char(
        string='Default Reply-To',
        config_parameter='mandrill_mail.default_reply_to',
        help='Reply-to address for emails sent from models without their own reply-to address. '
             'Leave empty to keep the reply-to address Odoo would normally use.',
    )
    mandrill_reply_tracking = fields.Boolean(
        string='Include Record Details',
        config_parameter='mandrill_mail.reply_tracking',
        help='Send the record an email was sent from as Mailchimp Transactional metadata and add a '
             'reference to the reply-to address, so replies are logged on that record '
             '(e.g. a reply to an invoice email is posted on the invoice).',
    )
    mandrill_track_opens = fields.Boolean(
        string='Track Opens', config_parameter='mandrill_mail.track_opens')
    mandrill_track_clicks = fields.Boolean(
        string='Track Clicks', config_parameter='mandrill_mail.track_clicks')
    mandrill_inbound_webhook_key = fields.Char(
        string='Inbound Webhook Key',
        config_parameter='mandrill_mail.inbound_webhook_key',
        help='Webhook key from Mandrill > Inbound > your domain. When set, incoming emails are only '
             'accepted when Mailchimp Transactional signed them with it.',
    )
    mandrill_log_retention_days = fields.Integer(
        string='Keep Email Log For',
        config_parameter='mandrill_mail.log_retention_days',
        help='Days to keep the email log. 0 keeps it forever.',
    )
    mandrill_inbound_url = fields.Char(string='Inbound Webhook URL', compute='_compute_mandrill_urls')
    mandrill_events_url = fields.Char(string='Events Webhook URL', compute='_compute_mandrill_urls')

    def _compute_mandrill_urls(self):
        service = self.env['mandrill.service']
        for settings in self:
            settings.mandrill_inbound_url = service._get_url(INBOUND_PATH)
            settings.mandrill_events_url = service._get_url(EVENTS_PATH)

    @api.onchange('mandrill_enabled')
    def _onchange_mandrill_enabled(self):
        # Mailchimp Transactional replaces the custom, Gmail and Outlook servers.
        if self.mandrill_enabled:
            self.external_email_server_default = False
            self.module_google_gmail = False
            self.module_microsoft_outlook = False

    def set_values(self):
        super().set_values()
        self.env['mandrill.service']._schedule_route_sync()

    # ------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------

    def _mandrill_notify(self, message, title=None, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title or _('Mailchimp Transactional'),
                'message': message,
                'type': kind,
                'sticky': kind != 'success',
            },
        }

    def action_mandrill_test_connection(self):
        try:
            self.env['mandrill.service']._get_api().ping()
        except MandrillError as e:
            raise UserError(_("Could not connect to Mailchimp Transactional:\n%s", e)) from e
        return self._mandrill_notify(_("Connected to Mailchimp Transactional."))

    def action_mandrill_sync(self):
        service = self.env['mandrill.service']
        if not service._is_enabled():
            raise UserError(_("Enable the Mailchimp Transactional Email Service and enter an API key first."))
        service._sync_inbound_routes(raise_on_error=True)
        service._sync_events_webhook()
        warnings = []
        client = service._get_api()
        for domain in service._inbound_domains():
            try:
                check = client.check_inbound_domain(domain)
            except MandrillError:
                continue
            if not check.get('valid_mx'):
                warnings.append(domain)
        if warnings:
            return self._mandrill_notify(
                _("Routes and webhook are set up, but the MX records of %s don't point to Mailchimp "
                  "Transactional yet, so incoming email won't arrive until they do.", ', '.join(warnings)),
                kind='warning')
        return self._mandrill_notify(_("Inbound routes and the delivery events webhook are set up."))

    def action_mandrill_open_reply_routes(self):
        return self.env['ir.actions.act_window']._for_xml_id('mandrill_mail.action_mandrill_reply_route')

    def action_mandrill_open_logs(self):
        return self.env['ir.actions.act_window']._for_xml_id('mandrill_mail.action_mandrill_mail_log')

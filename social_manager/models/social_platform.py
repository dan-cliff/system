from odoo import api, fields, models
from odoo.exceptions import UserError

from ..providers import PROVIDER_CODES, get_provider_class


class SocialPlatform(models.Model):
    _name = 'social.platform'
    _inherit = ['social.access.mixin', 'mail.thread']
    _description = 'Social Platform'
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    # Technical: picks the API integration the code uses, so it stays a fixed selection.
    code = fields.Selection(PROVIDER_CODES, string='Integration', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    image_128 = fields.Image(string='Logo', max_width=128, max_height=128)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    # OAuth app credentials (from the platform's developer portal)
    client_id = fields.Char(string='Client ID / App ID', tracking=True, groups='social_manager.group_social_manager')
    client_secret = fields.Char(string='Client Secret / App Secret', groups='social_manager.group_social_manager')
    auth_url = fields.Char(string='Authorisation URL', groups='social_manager.group_social_manager')
    token_url = fields.Char(string='Token URL', groups='social_manager.group_social_manager')
    api_base_url = fields.Char(string='API Base URL', groups='social_manager.group_social_manager')
    scopes = fields.Char(string='Scopes', groups='social_manager.group_social_manager',
                         help='Permissions requested when connecting an account.')
    redirect_uri = fields.Char(string='OAuth Redirect URI', compute='_compute_redirect_uri',
                               help='Register this URL as the redirect / callback URL of your app '
                                    'in the platform\'s developer portal.')
    developer_portal_url = fields.Char(string='Developer Portal', compute='_compute_provider_info')
    setup_notes = fields.Text(string='Setup Notes', compute='_compute_provider_info')
    is_configured = fields.Boolean(compute='_compute_is_configured')

    # Monetisation
    is_monetised = fields.Boolean(string='Monetised', tracking=True,
                                  help='Income is earned from content on this platform.')
    partner_id = fields.Many2one('res.partner', string='Paying Partner', tracking=True,
                                 help='Who pays the monetisation income - the customer on the '
                                      'invoices Social Manager creates for this platform.')

    account_ids = fields.One2many('social.account', 'platform_id', string='Connected Accounts')
    channel_ids = fields.One2many('social.channel', 'platform_id', string='Pages / Channels')
    account_count = fields.Integer(compute='_compute_counts')
    channel_count = fields.Integer(compute='_compute_counts')
    post_count = fields.Integer(compute='_compute_counts')
    income_ids = fields.One2many('social.income', 'platform_id', string='Income')
    income_total = fields.Monetary(string='Total Income', compute='_compute_income')
    income_uninvoiced = fields.Monetary(string='Not Yet Invoiced', compute='_compute_income')

    @api.depends('code')
    def _compute_redirect_uri(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for platform in self:
            platform.redirect_uri = '%s/social_manager/oauth/callback' % base_url.rstrip('/')

    @api.depends('code')
    def _compute_provider_info(self):
        for platform in self:
            provider = get_provider_class(platform.code)
            platform.developer_portal_url = provider.developer_portal_url if provider else False
            platform.setup_notes = provider.setup_notes if provider else False

    @api.depends('code')
    def _compute_is_configured(self):
        for platform in self:
            platform.is_configured = bool(platform.sudo().client_id and platform.sudo().client_secret)

    def _compute_counts(self):
        for platform in self:
            platform.account_count = len(platform.account_ids)
            platform.channel_count = len(platform.channel_ids)
            platform.post_count = self.env['social.post'].search_count(
                [('channel_ids.platform_id', '=', platform.id)])

    @api.depends('income_ids.amount', 'income_ids.invoice_line_id')
    def _compute_income(self):
        for platform in self:
            incomes = platform.income_ids
            platform.income_total = sum(incomes.mapped('amount'))
            platform.income_uninvoiced = sum(incomes.filtered(lambda i: not i.invoice_line_id).mapped('amount'))

    @api.onchange('code')
    def _onchange_code(self):
        """Fill the OAuth endpoints and scopes with the integration's defaults."""
        provider = get_provider_class(self.code)
        if provider:
            self.auth_url = provider.default_auth_url
            self.token_url = provider.default_token_url
            self.api_base_url = provider.default_api_base_url
            self.scopes = provider.default_scopes
            if not self.name:
                self.name = provider.label

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            provider = get_provider_class(vals.get('code'))
            if provider:
                vals.setdefault('auth_url', provider.default_auth_url)
                vals.setdefault('token_url', provider.default_token_url)
                vals.setdefault('api_base_url', provider.default_api_base_url)
                vals.setdefault('scopes', provider.default_scopes)
        return super().create(vals_list)

    def _social_access_label(self):
        self.ensure_one()
        return self.name

    def _social_access_sequence(self):
        return self.sequence or 10

    def _get_provider(self, account=None):
        self.ensure_one()
        provider_class = get_provider_class(self.code)
        if not provider_class:
            raise UserError('The integration of %s is not available.' % self.name)
        return provider_class(self.sudo(), account=account)

    def action_reset_endpoints(self):
        for platform in self:
            provider = get_provider_class(platform.code)
            if provider:
                platform.sudo().write({
                    'auth_url': provider.default_auth_url,
                    'token_url': provider.default_token_url,
                    'api_base_url': provider.default_api_base_url,
                    'scopes': provider.default_scopes,
                })
        return True

    def action_connect(self):
        """Start the OAuth sign-in for this platform."""
        self.ensure_one()
        if not self.is_configured:
            raise UserError(
                'Enter the Client ID and Client Secret of your %s app first, and register the '
                'OAuth Redirect URI shown on this form in the app.' % self.name
            )
        return {
            'type': 'ir.actions.act_url',
            'url': '/social_manager/oauth/start/%s' % self.id,
            'target': 'self',
        }

    def action_open_developer_portal(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.developer_portal_url, 'target': 'new'}

    def action_view_channels(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_channel')
        action['domain'] = [('platform_id', '=', self.id)]
        action['context'] = {'default_platform_id': self.id}
        return action

    def action_view_accounts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_account')
        action['domain'] = [('platform_id', '=', self.id)]
        action['context'] = {'default_platform_id': self.id}
        return action

    def action_view_posts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_post')
        action['domain'] = [('channel_ids.platform_id', '=', self.id)]
        return action

    def action_view_income(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_income')
        action['domain'] = [('platform_id', '=', self.id)]
        action['context'] = {'search_default_group_channel': 1}
        return action

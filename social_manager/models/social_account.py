import logging
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    """One OAuth sign-in to a platform. It holds the user token and imports the
    Pages / Channels that sign-in can manage."""
    _name = 'social.account'
    _inherit = ['mail.thread']
    _description = 'Connected Social Account'
    _order = 'platform_id, name'

    name = fields.Char(required=True, tracking=True)
    platform_id = fields.Many2one('social.platform', string='Platform', required=True,
                                  ondelete='cascade', index=True)
    platform_code = fields.Selection(related='platform_id.code')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Connected By', default=lambda self: self.env.user,
                              readonly=True)
    external_id = fields.Char(string='Account ID', readonly=True)
    image_url = fields.Char(readonly=True)
    access_token = fields.Char(groups='base.group_system', copy=False)
    refresh_token = fields.Char(groups='base.group_system', copy=False)
    token_expiry = fields.Datetime(string='Token Expires', readonly=True, copy=False)
    granted_scopes = fields.Char(readonly=True)
    connected_date = fields.Datetime(string='Connected On', readonly=True)
    # Technical connection state, set by the code.
    state = fields.Selection([
        ('connected', 'Connected'),
        ('expired', 'Needs Reconnecting'),
        ('error', 'Error'),
    ], default='connected', readonly=True, tracking=True)
    last_error = fields.Text(readonly=True)
    active = fields.Boolean(default=True)
    channel_ids = fields.One2many('social.channel', 'account_id', string='Pages / Channels')
    channel_count = fields.Integer(compute='_compute_channel_count')

    def _compute_channel_count(self):
        for account in self:
            account.channel_count = len(account.channel_ids)

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    def _store_token(self, token):
        """Save a token response ({access_token, refresh_token, expires_in, scope})."""
        vals = {'state': 'connected', 'last_error': False}
        if token.get('access_token'):
            vals['access_token'] = token['access_token']
        if token.get('refresh_token'):
            vals['refresh_token'] = token['refresh_token']
        if token.get('expires_in'):
            vals['token_expiry'] = fields.Datetime.now() + timedelta(seconds=int(token['expires_in']))
        if token.get('scope'):
            scope = token['scope']
            vals['granted_scopes'] = ' '.join(scope) if isinstance(scope, list) else scope
        self.sudo().write(vals)

    def _get_access_token(self):
        """A valid access token, refreshed first when it has (nearly) expired."""
        self.ensure_one()
        account = self.sudo()
        expiring = account.token_expiry and account.token_expiry <= fields.Datetime.now() + timedelta(minutes=5)
        if expiring and account.refresh_token:
            try:
                token = account.platform_id._get_provider(account).refresh_access_token(account.refresh_token)
                account._store_token(token)
            except UserError as exc:
                account.write({'state': 'expired', 'last_error': str(exc)})
                raise
        elif expiring:
            account.state = 'expired'
            raise UserError('The %s connection "%s" has expired - reconnect it from Platforms.'
                            % (account.platform_id.name, account.name))
        return account.access_token

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_sync_channels(self):
        """Import / update the Pages / Channels this account can manage."""
        for account in self:
            provider = account.platform_id._get_provider(account)
            try:
                channels = provider.discover_channels()
            except UserError as exc:
                account.sudo().write({'state': 'error', 'last_error': str(exc)})
                raise
            account._update_channels(channels)
        return True

    def _update_channels(self, channels):
        """Create or update social.channel records from provider data dicts."""
        self.ensure_one()
        Channel = self.env['social.channel'].sudo().with_context(active_test=False)
        for data in channels:
            channel = Channel.search([
                ('platform_id', '=', self.platform_id.id),
                ('external_id', '=', data['external_id']),
            ], limit=1)
            vals = {
                'name': data.get('name') or data['external_id'],
                'account_id': self.id,
                'platform_id': self.platform_id.id,
                'external_id': data['external_id'],
                'external_username': data.get('username'),
                'external_url': data.get('url'),
                'image_url': data.get('image_url'),
                'follower_count': data.get('follower_count') or 0,
                'connection_state': 'connected',
                'last_error': False,
            }
            if data.get('access_token'):
                vals['access_token'] = data['access_token']
            if channel:
                channel.write(vals)
            else:
                vals['company_id'] = self.company_id.id
                vals['is_monetised'] = self.platform_id.is_monetised
                Channel.create(vals)

    def action_reconnect(self):
        self.ensure_one()
        return self.platform_id.action_connect()

    def action_view_channels(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_channel')
        action['domain'] = [('account_id', '=', self.id)]
        return action

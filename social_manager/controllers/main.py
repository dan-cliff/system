"""OAuth sign-in for Social Manager platforms.

/social_manager/oauth/start/<platform> sends the user to the platform's
authorisation page; the platform redirects back to /social_manager/oauth/callback
(the Redirect URI shown on the Platform form) with a code, which is exchanged
for a token. The account and every Page / Channel it manages are then saved.
"""
import base64
import hashlib
import logging
import secrets

from odoo import fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

SESSION_KEY = 'social_manager_oauth'


class SocialManagerOAuth(http.Controller):

    def _back(self, model, res_id=None):
        url = '/odoo/action-social_manager.action_social_platform'
        if model == 'social.account' and res_id:
            url = '/odoo/action-social_manager.action_social_account/%s' % res_id
        elif res_id:
            url = '%s/%s' % (url, res_id)
        return request.redirect(url)

    @http.route('/social_manager/oauth/start/<int:platform_id>', type='http', auth='user')
    def oauth_start(self, platform_id, **kwargs):
        if not request.env.user.has_group('social_manager.group_social_manager'):
            raise AccessError('Only Social Manager administrators can connect accounts.')
        platform = request.env['social.platform'].browse(platform_id).exists()
        if not platform:
            return request.not_found()
        provider = platform._get_provider()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)[:96] if provider.use_pkce else None
        challenge = None
        if verifier:
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        # A copy: the session only saves a key whose value changed.
        pending = dict(request.session.get(SESSION_KEY) or {})
        pending[state] = {'platform_id': platform.id, 'verifier': verifier,
                          'company_id': request.env.company.id}
        request.session[SESSION_KEY] = pending
        return request.redirect(provider.authorize_url(state, platform.redirect_uri, challenge), local=False)

    @http.route('/social_manager/oauth/callback', type='http', auth='user')
    def oauth_callback(self, state=None, code=None, error=None, error_description=None, **kwargs):
        pending = dict(request.session.get(SESSION_KEY) or {})
        data = pending.pop(state, None) if state else None
        request.session[SESSION_KEY] = pending
        if not data:
            return request.make_response(
                'This sign-in link has expired or was not started from Social Manager. '
                'Please start again from Social Manager > Platforms.', status=400)
        Platform = request.env['social.platform'].with_company(data['company_id'])
        platform = Platform.browse(data['platform_id']).exists()
        if not platform:
            return request.not_found()
        if error or not code:
            platform.message_post(body='Connecting an account was cancelled or refused: %s'
                                  % (error_description or error or 'no code returned'))
            return self._back('social.platform', platform.id)
        provider = platform._get_provider()
        try:
            token = provider.exchange_code(code, platform.redirect_uri, data.get('verifier'))
            if not token.get('access_token'):
                raise UserError('%s did not return an access token: %s' % (platform.name, token))
            info = provider.get_account_info(token['access_token'])
            account = self._save_account(platform, token, info)
            account.action_sync_channels()
        except UserError as exc:
            _logger.warning('Social Manager: connecting %s failed: %s', platform.name, exc)
            platform.message_post(body='Connecting an account failed: %s' % exc)
            return self._back('social.platform', platform.id)
        platform.message_post(body='Account "%s" connected by %s (%d Pages / Channels).'
                              % (account.name, request.env.user.name, len(account.channel_ids)))
        return self._back('social.account', account.id)

    def _save_account(self, platform, token, info):
        Account = request.env['social.account'].sudo().with_context(active_test=False)
        account = Account.search([('platform_id', '=', platform.id),
                                  ('external_id', '=', info.get('external_id'))], limit=1)
        vals = {
            'name': info.get('name') or platform.name,
            'platform_id': platform.id,
            'external_id': info.get('external_id'),
            'image_url': info.get('image_url'),
            'user_id': request.env.user.id,
            'connected_date': fields.Datetime.now(),
            'active': True,
        }
        if account:
            account.write(vals)
        else:
            vals['company_id'] = platform.company_id.id
            account = Account.create(vals)
        account._store_token(token)
        return account.sudo(False)

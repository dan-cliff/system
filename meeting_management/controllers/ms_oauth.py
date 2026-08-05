import logging
import json
import requests
from datetime import datetime, timedelta

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MicrosoftOAuthController(http.Controller):
    """Handles the Microsoft OAuth 2.0 callback for Teams/Outlook integration."""

    @http.route(
        '/meeting_management/ms_oauth/callback',
        type='http',
        auth='user',
        website=False,
    )
    def ms_oauth_callback(self, code=None, state=None, error=None, **kwargs):
        """Process the Microsoft OAuth authorization code."""
        if error:
            _logger.error("Microsoft OAuth error: %s", error)
            return request.redirect('/web#action=meeting_management.action_res_config_settings&error=oauth_error')

        if not code:
            return request.redirect('/web#action=meeting_management.action_res_config_settings&error=no_code')

        IrConfigParam = request.env['ir.config_parameter'].sudo()
        client_id = IrConfigParam.get_param('meeting_management.ms_client_id', '')
        client_secret = IrConfigParam.get_param('meeting_management.ms_client_secret', '')
        tenant_id = IrConfigParam.get_param('meeting_management.ms_tenant_id', 'common')
        redirect_uri = IrConfigParam.get_param('meeting_management.ms_redirect_uri', '')

        token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }

        try:
            resp = requests.post(token_url, data=payload, timeout=15)
            resp.raise_for_status()
            token_data = resp.json()
        except Exception as e:
            _logger.error("Microsoft token exchange failed: %s", e)
            return request.redirect('/web#action=meeting_management.action_res_config_settings&error=token_exchange')

        access_token = token_data.get('access_token', '')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)
        expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        IrConfigParam.set_param('meeting_management.ms_access_token', access_token)
        IrConfigParam.set_param('meeting_management.ms_refresh_token', refresh_token)
        IrConfigParam.set_param('meeting_management.ms_token_expiry', expiry)

        return request.redirect('/web#action=meeting_management.action_res_config_settings&success=connected')

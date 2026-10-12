"""Shared plumbing for the platform integrations.

Each integration subclasses SocialProvider and implements the OAuth sign-in,
Page / Channel discovery, publishing, metrics, comments and moderation for
its platform. Methods return plain dicts so the models stay platform-neutral.
"""
import base64
import logging
from urllib.parse import urlencode

import requests

from odoo import fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 60
UPLOAD_TIMEOUT = 600


class SocialProvider:
    code = None
    label = None
    default_auth_url = ''
    default_token_url = ''
    default_api_base_url = ''
    default_scopes = ''
    scope_separator = ' '
    developer_portal_url = ''
    setup_notes = ''
    use_pkce = False
    # Some platforms call the client id something else in the authorise URL.
    client_id_param = 'client_id'
    supports_comments = True
    supports_delete = True

    def __init__(self, platform, account=None):
        self.platform = platform
        self.env = platform.env
        self.account = account

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _api_url(self, path):
        if path.startswith('http'):
            return path
        return '%s/%s' % ((self.platform.api_base_url or self.default_api_base_url).rstrip('/'), path.lstrip('/'))

    def _headers(self, token):
        return {'Authorization': 'Bearer %s' % token} if token else {}

    def _request(self, method, path, token=None, headers=None, raw=False, timeout=TIMEOUT, **kwargs):
        all_headers = self._headers(token)
        all_headers.update(headers or {})
        url = self._api_url(path)
        try:
            response = requests.request(method, url, headers=all_headers, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            _logger.warning('%s API call to %s failed: %s', self.label, url, exc)
            raise UserError('Could not reach %s: %s' % (self.label, exc)) from exc
        if response.status_code >= 400:
            raise UserError('%s error (%s): %s' % (self.label, response.status_code, self._error_message(response)))
        if raw:
            return response
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {'_text': response.text}

    def _error_message(self, response):
        try:
            data = response.json()
        except ValueError:
            return response.text[:500]
        error = data.get('error') if isinstance(data, dict) else None
        if isinstance(error, dict):
            return error.get('message') or error.get('error_user_msg') or str(error)
        if isinstance(data, dict):
            return (data.get('error_description') or data.get('message') or data.get('detail')
                    or data.get('title') or error or str(data))[:500]
        return str(data)[:500]

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------
    def _scopes(self):
        scopes = (self.platform.scopes or self.default_scopes or '').replace(',', ' ').split()
        return self.scope_separator.join(scopes)

    def authorize_url(self, state, redirect_uri, code_challenge=None):
        params = {
            self.client_id_param: self.platform.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self._scopes(),
            'state': state,
        }
        if self.use_pkce and code_challenge:
            params.update({'code_challenge': code_challenge, 'code_challenge_method': 'S256'})
        params.update(self._extra_authorize_params())
        return '%s?%s' % (self.platform.auth_url or self.default_auth_url, urlencode(params))

    def _extra_authorize_params(self):
        return {}

    def exchange_code(self, code, redirect_uri, code_verifier=None):
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': self.platform.client_id,
            'client_secret': self.platform.client_secret,
        }
        if self.use_pkce and code_verifier:
            data['code_verifier'] = code_verifier
        return self._request('POST', self.platform.token_url or self.default_token_url, data=data)

    def refresh_access_token(self, refresh_token):
        return self._request('POST', self.platform.token_url or self.default_token_url, data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.platform.client_id,
            'client_secret': self.platform.client_secret,
        })

    def get_account_info(self, token):
        """{external_id, name, image_url} of the signed-in user / organisation."""
        raise NotImplementedError

    def _account_token(self):
        if not self.account:
            raise UserError('This %s Page / Channel is not connected to an account.' % self.label)
        return self.account._get_access_token()

    # ------------------------------------------------------------------
    # Pages / Channels and posts
    # ------------------------------------------------------------------
    def discover_channels(self):
        """[{external_id, name, username, url, image_url, follower_count, access_token?}, ...]"""
        raise NotImplementedError

    def check_post(self, post, channel):
        """Raise UserError when `post` can't be published on `channel` (e.g. a video is required)."""
        return True

    def publish(self, post, channel):
        """Publish and return {external_id, url}."""
        raise NotImplementedError

    def fetch_metrics(self, publication):
        """{likes_count, reactions_count, comments_count, shares_count, views_count} (any subset)."""
        return {}

    def fetch_comments(self, publication):
        """[{external_id, parent_id, author_name, author_id, message, date, likes, is_own}, ...],
        parents before their replies."""
        return []

    def reply_comment(self, comment, text):
        raise UserError('Replying to comments is not supported on %s.' % self.label)

    def hide_comment(self, comment, hidden):
        raise UserError('Hiding comments is not supported on %s.' % self.label)

    def delete_comment(self, comment):
        raise UserError('Deleting comments is not supported on %s.' % self.label)

    def delete_post(self, publication):
        raise UserError('Deleting posts through the API is not supported on %s - delete it on %s.'
                        % (self.label, self.label))

    def fetch_income(self, channel, date_from, date_to):
        """[{ref, date, amount, name, publication_external_id?}, ...]. Platforms without an
        income API return nothing; their income is entered by hand."""
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _post_text(post):
        text = post.message or ''
        if post.link_url and post.link_url not in text:
            text = ('%s\n\n%s' % (text, post.link_url)).strip()
        return text

    @staticmethod
    def _images(post):
        return post.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith('image/'))

    @staticmethod
    def _videos(post):
        return post.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith('video/'))

    @staticmethod
    def _attachment_bytes(attachment):
        return base64.b64decode(attachment.sudo().datas or b'')

    def _public_url(self, attachment):
        """A URL the platform can download the attachment from (some APIs only take URLs)."""
        attachment = attachment.sudo()
        token = attachment.generate_access_token()[0]
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        return '%s/web/content/%s?access_token=%s' % (base_url, attachment.id, token)

    @staticmethod
    def _parse_datetime(value):
        """A platform timestamp (ISO 8601 or epoch seconds/ms) as a naive UTC datetime, or False."""
        if not value:
            return False
        from datetime import datetime, timezone
        try:
            if isinstance(value, (int, float)):
                seconds = value / 1000.0 if value > 10 ** 11 else value
                return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
            text = str(value).replace('Z', '+00:00')
            if len(text) > 5 and text[-5] in '+-' and text[-3] != ':':
                text = text[:-2] + ':' + text[-2:]  # +0000 -> +00:00
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError, OSError):
            return False

    @staticmethod
    def _date_param(value):
        return fields.Date.to_string(value)

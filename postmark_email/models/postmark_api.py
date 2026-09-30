import hashlib
import hmac
import logging
import re
from datetime import datetime, timezone

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

POSTMARK_API_URL = 'https://api.postmarkapp.com'
POSTMARK_REQUEST_TIMEOUT = 20

# ir.config_parameter keys used by this module
PARAM_PREFIX = 'postmark_email.'
PARAM_ENABLED = PARAM_PREFIX + 'enabled'
PARAM_SERVER_TOKEN = PARAM_PREFIX + 'server_token'
PARAM_FROM_FILTER = PARAM_PREFIX + 'from_filter'
PARAM_DEFAULT_STREAM = PARAM_PREFIX + 'default_stream_id'
PARAM_FALLBACK_REPLY_TO = PARAM_PREFIX + 'fallback_reply_to'
PARAM_RECORD_ROUTING = PARAM_PREFIX + 'record_routing'
PARAM_ALIAS_STREAMS = PARAM_PREFIX + 'alias_streams'
PARAM_BLACKLIST_SPAM = PARAM_PREFIX + 'blacklist_spam'
PARAM_WEBHOOK_USER = PARAM_PREFIX + 'webhook_user'
PARAM_WEBHOOK_PASSWORD = PARAM_PREFIX + 'webhook_password'

INBOUND_WEBHOOK_PATH = '/postmark/webhook/inbound'
EVENTS_WEBHOOK_PATH = '/postmark/webhook/events'


class PostmarkError(Exception):
    """An error answered by the Postmark API (or the request to it)."""

    def __init__(self, message, error_code=None, status=None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status = status


def parse_postmark_datetime(value):
    """Turn a Postmark ISO 8601 timestamp into a naive UTC datetime.

    Postmark sends up to 7 fractional digits and an offset or ``Z``
    (e.g. ``2014-02-17T07:25:01.4178645-05:00``), which ``fromisoformat``
    does not reliably accept, so the fraction is trimmed to microseconds.
    """
    if not value:
        return False
    value = value.strip().replace('Z', '+00:00')
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class PostmarkApi(models.AbstractModel):
    _name = 'postmark.api'
    _description = 'Postmark API'

    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _is_enabled(self):
        return bool(self._get_param(PARAM_ENABLED))

    @api.model
    def _is_configured(self):
        return self._is_enabled() and bool((self._get_param(PARAM_SERVER_TOKEN) or '').strip())

    @api.model
    def _calls_disabled(self):
        """No calls to Postmark while running tests or loading the registry."""
        return self.env['ir.mail_server']._disable_send()

    @api.model
    def _request(self, method, path, payload=None, params=None):
        """Call the Postmark API with the server token and return its JSON.

        Raises PostmarkError when Postmark answers with an error (non-2xx or
        a non-zero ErrorCode) or can't be reached.
        """
        token = (self._get_param(PARAM_SERVER_TOKEN) or '').strip()
        if not token:
            raise PostmarkError(_(
                "The Postmark Server API Token is not set in Settings > General Settings > Emails."))
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Postmark-Server-Token': token,
        }
        try:
            response = requests.request(
                method, POSTMARK_API_URL + path, json=payload, params=params,
                headers=headers, timeout=POSTMARK_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise PostmarkError(_("Could not reach Postmark: %s", e)) from e
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {'_items': data}
        error_code = data.get('ErrorCode')
        if response.status_code >= 400 or error_code:
            message = data.get('Message') or response.text or response.reason
            raise PostmarkError(
                _("Postmark error %(code)s: %(message)s",
                  code=error_code or response.status_code, message=message),
                error_code=error_code, status=response.status_code)
        return data

    # ------------------------------------------------------------------
    # Reply tokens: "<model>-<res_id>-<signature>", added to the Reply-To as
    # a plus address (invoices+account.move-42-1a2b3c4d5e@...). Postmark
    # hands it back as the MailboxHash of the reply.
    # ------------------------------------------------------------------

    @api.model
    def _record_token_signature(self, model, res_id):
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        message = f'postmark-reply:{model}:{res_id}'
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()[:10]

    @api.model
    def _record_token(self, model, res_id):
        return f'{model}-{res_id}-{self._record_token_signature(model, res_id)}'

    @api.model
    def _parse_record_token(self, token):
        """Return ``(model, res_id)`` for a valid token of an existing record."""
        match = re.fullmatch(r'([a-z0-9_.]+)-(\d+)-([0-9a-f]{10})', (token or '').strip().lower())
        if not match:
            return None, None
        model, res_id, signature = match.group(1), int(match.group(2)), match.group(3)
        if not hmac.compare_digest(signature, self._record_token_signature(model, res_id)):
            return None, None
        if model not in self.env or not self.env[model].browse(res_id).exists():
            return None, None
        return model, res_id

    @api.model
    def _user_error(self, error):
        return UserError(error.message if isinstance(error, PostmarkError) else str(error))

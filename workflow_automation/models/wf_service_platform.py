# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import datetime
import json
import logging
import re
import time as _time

import requests
from requests.exceptions import RequestException

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Response keys to probe (in order) when extracting a token from a
# username/password authentication response.
_TOKEN_KEYS = (
    'token',
    'access_token',
    'session_token',
    'api_key',
    'key',
    'jwt',
    'id_token',
)

# Headers whose values should be redacted before writing to the API call log.
_SENSITIVE_HEADERS = frozenset({'authorization', 'x-api-key', 'x-auth-token'})

# Credential field names whose values are considered secrets and should be
# redacted in log output.
_SECRET_CREDENTIAL_FIELDS = frozenset({'password', 'client_secret'})

# Regex for {{placeholder}} substitution in JSON body text and header values.
_PLACEHOLDER_RE = re.compile(r'\{\{(\w+)\}\}')


def _redact_headers(headers_dict):
    """Return a copy of *headers_dict* with sensitive values replaced."""
    return {
        k: ('***REDACTED***' if k.lower() in _SENSITIVE_HEADERS else v)
        for k, v in (headers_dict or {}).items()
    }


class WfServicePlatform(models.Model):
    """Service / Platform authentication configuration.

    Stores authentication credentials for external services and platforms,
    supporting both username / password and OAuth 2.0 client-credentials
    flows.

    Calling ``_authenticate()`` on a linked record from any other model
    will perform the configured authentication handshake, write a full
    entry to ``wf.api.call.log``, and return a standardised result dict::

        result = self.service_platform_id._authenticate(
            caller_model='wf.automation',
            caller_res_id=self.id,
        )
        token = result['token']
        raw   = result['raw']

    Request body construction (in priority order)
    ---------------------------------------------
    1. **JSON override** (``auth_request_body`` field) — used as-is;
       ``{{username}}``, ``{{password}}``, ``{{client_id}}``, and
       ``{{client_secret}}`` placeholders are substituted before the
       text is parsed as JSON.
    2. **Body parameters table** (``body_param_ids``) — rows are assembled
       into a dict in sequence order; ``credential`` rows resolve the stored
       value at call time so secrets never appear in the table itself.
    3. **Default body** for the selected authentication type.

    Custom request headers (``header_ids``) are merged on top of the
    default ``Content-Type: application/json`` / ``Accept: application/json``
    headers, allowing additions or overrides.  Header values also support
    ``{{credential}}`` placeholders.
    """

    _name = 'wf.service.platform'
    _description = 'Service / Platform'
    _order = 'name'

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------ #
    # Authentication type                                                  #
    # ------------------------------------------------------------------ #

    auth_type = fields.Selection(
        selection=[
            ('basic', 'Username & Password'),
            ('oauth2', 'OAuth 2.0 (Client Credentials)'),
        ],
        string='Authentication Type',
        required=True,
        default='basic',
    )

    body_format = fields.Selection(
        selection=[
            ('json', 'JSON  (application/json)'),
            ('form', 'Form Encoded  (application/x-www-form-urlencoded)'),
        ],
        string='Request Body Format',
        required=True,
        default='json',
        help=(
            'Controls how the request body is serialised and which '
            'Content-Type header is sent.\n\n'
            'JSON (default): body is sent as a JSON object with '
            'Content-Type: application/json.  Works with most modern REST APIs.\n\n'
            'Form Encoded: body is sent as URL-encoded key/value pairs with '
            'Content-Type: application/x-www-form-urlencoded.  Required by '
            'Microsoft Azure AD, many legacy OAuth 2.0 providers, and any '
            'service that rejects a JSON body.'
        ),
    )

    # ------------------------------------------------------------------ #
    # Username & Password credentials                                      #
    # ------------------------------------------------------------------ #

    username = fields.Char(string='Username')
    password = fields.Char(string='Password')

    # ------------------------------------------------------------------ #
    # OAuth 2.0 credentials                                                #
    # ------------------------------------------------------------------ #

    client_id = fields.Char(string='Client ID')
    client_secret = fields.Char(string='Client Secret')

    # ------------------------------------------------------------------ #
    # Shared endpoint                                                      #
    # ------------------------------------------------------------------ #

    base_url = fields.Char(
        string='Base URL',
        help=(
            'Root URL of this service\'s API '
            '(e.g. https://api.example.com/v1).\n'
            'Workflow API Call steps append a relative URL path to this '
            'base for each outbound request.'
        ),
    )

    auth_endpoint = fields.Char(
        string='Authentication Endpoint',
        required=True,
        help=(
            'Full URL of the authentication endpoint.\n'
            'Example: https://api.example.com/oauth/token'
        ),
    )

    response_token_key = fields.Char(
        string='Response API Key',
        help=(
            'Key (or dot-separated path) in the JSON response that holds the '
            'access token.\n'
            'Examples:\n'
            '  access_token          — top-level key\n'
            '  data.token            — nested key\n'
            '  result.auth.jwt       — deeply nested key\n\n'
            'When set this takes priority over the built-in token detection. '
            'Leave empty to use automatic detection.'
        ),
    )

    # ------------------------------------------------------------------ #
    # Custom request headers (child table)                                 #
    # ------------------------------------------------------------------ #

    header_ids = fields.One2many(
        'wf.service.platform.header',
        'platform_id',
        string='Custom Headers',
    )

    # ------------------------------------------------------------------ #
    # Request body — params table + JSON override                         #
    # ------------------------------------------------------------------ #

    body_param_ids = fields.One2many(
        'wf.service.platform.body.param',
        'platform_id',
        string='Body Parameters',
    )

    auth_request_body = fields.Text(
        string='JSON Override',
        help=(
            'Optional — completely overrides the Body Parameters table and the\n'
            'default body for the selected authentication type.\n\n'
            'Supports credential placeholders:\n'
            '  {{username}}      — resolved from the Username field\n'
            '  {{password}}      — resolved from the Password field\n'
            '  {{client_id}}     — resolved from the Client ID field\n'
            '  {{client_secret}} — resolved from the Client Secret field\n\n'
            'Example:\n'
            '  {"grant_type": "password",\n'
            '   "username": "{{username}}",\n'
            '   "password": "{{password}}"}'
        ),
    )

    # ------------------------------------------------------------------ #
    # Token cache (populated automatically by _authenticate)              #
    # ------------------------------------------------------------------ #

    last_token = fields.Char(
        string='Cached Token',
        readonly=True,
        copy=False,
        help='The most recently retrieved access token (truncated at 1 024 characters).',
    )
    last_token_expiry = fields.Datetime(
        string='Token Expiry',
        readonly=True,
        copy=False,
    )
    last_authenticated = fields.Datetime(
        string='Last Authenticated',
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------ #
    # Computed — count of related API call logs                           #
    # ------------------------------------------------------------------ #

    api_call_log_count = fields.Integer(
        string='API Call Logs',
        compute='_compute_api_call_log_count',
    )

    def _compute_api_call_log_count(self):
        data = self.env['wf.api.call.log'].read_group(
            domain=[('service_platform_id', 'in', self.ids)],
            fields=['service_platform_id'],
            groupby=['service_platform_id'],
        )
        counts = {d['service_platform_id'][0]: d['service_platform_id_count'] for d in data}
        for rec in self:
            rec.api_call_log_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------ #
    # Smart-button action — open related logs                             #
    # ------------------------------------------------------------------ #

    def action_view_api_call_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('API Call Logs — %s') % self.name,
            'res_model': 'wf.api.call.log',
            'view_mode': 'list,form',
            'domain': [('service_platform_id', '=', self.id)],
            'context': {'default_service_platform_id': self.id},
        }

    # ------------------------------------------------------------------ #
    # UI action — Test from form view                                      #
    # ------------------------------------------------------------------ #

    def action_test_authentication(self):
        """Trigger authentication from the UI and return a notification."""
        self.ensure_one()
        try:
            result = self.sudo()._authenticate(call_name='Test Authentication')
            token = result.get('token') or ''
            preview = token[:30] + ('…' if len(token) > 30 else '')
            message = _('Authentication successful!') + (
                (' — Token: %s' % preview) if preview else ''
            )
            msg_type = 'success'
            sticky = False
        except Exception as exc:
            message = _('Authentication failed: %s') % str(exc)
            msg_type = 'danger'
            sticky = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': msg_type,
                'sticky': sticky,
            },
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_key_path(self, data, key_path):
        """Navigate a dot-separated *key_path* into *data* and return the value.

        For example, given ``data = {"result": {"auth": {"jwt": "tok123"}}}``
        and ``key_path = "result.auth.jwt"``, returns ``"tok123"``.

        Returns ``None`` (not raising) if any segment is missing or if an
        intermediate value is not a dict.
        """
        val = data
        for segment in key_path.split('.'):
            if not isinstance(val, dict):
                return None
            val = val.get(segment)
        # Only return string values — we don't want to cache a dict/int/etc.
        return val if isinstance(val, str) else None

    def _credential_map(self):
        """Return a dict of all credential field values keyed by field name."""
        self.ensure_one()
        return {
            'username':      self.username or '',
            'password':      self.password or '',
            'client_id':     self.client_id or '',
            'client_secret': self.client_secret or '',
        }

    def _substitute_placeholders(self, text, credentials):
        """Replace ``{{field_name}}`` tokens in *text* using *credentials*.

        Unknown placeholder names are left untouched.
        """
        def replacer(match):
            key = match.group(1)
            return credentials.get(key, match.group(0))
        return _PLACEHOLDER_RE.sub(replacer, text)

    def _build_request_headers(self, credentials):
        """Return the final headers dict for the authentication request.

        Starts with defaults (Content-Type driven by ``body_format``), then
        overlays rows from ``header_ids`` in sequence order.  Header *values*
        support ``{{credential}}`` placeholders.
        """
        content_type = (
            'application/x-www-form-urlencoded'
            if self.body_format == 'form'
            else 'application/json'
        )
        headers = {
            'Content-Type': content_type,
            'Accept': 'application/json',
        }
        for row in self.header_ids.sorted('sequence'):
            resolved_value = self._substitute_placeholders(row.value or '', credentials)
            headers[row.name] = resolved_value
        return headers

    def _build_request_body(self, credentials):
        """Return ``(body_dict, logged_body_dict)`` for the authentication request.

        *body_dict* contains the actual values (including live credentials).
        *logged_body_dict* is a sanitised copy safe to write to the API call
        log (secret credential fields are replaced with ``***REDACTED***``).

        Priority:
        1. JSON override field (placeholders resolved, then JSON-parsed).
        2. Body params table (rows assembled in sequence order).
        3. Default body for the selected ``auth_type``.

        Raises :class:`~odoo.exceptions.UserError` if the JSON override is
        set but cannot be parsed.
        """
        # ---- 1. JSON override -------------------------------------------
        if (self.auth_request_body or '').strip():
            raw_text = self._substitute_placeholders(
                self.auth_request_body, credentials
            )
            try:
                body = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise UserError(
                    _('Invalid JSON in JSON Override for "%s": %s') % (self.name, exc)
                ) from exc

            # Sanitise for logging: re-substitute with redacted values
            redacted_credentials = {
                k: ('***REDACTED***' if k in _SECRET_CREDENTIAL_FIELDS else v)
                for k, v in credentials.items()
            }
            logged_text = self._substitute_placeholders(
                self.auth_request_body, redacted_credentials
            )
            try:
                logged_body = json.loads(logged_text)
            except Exception:
                logged_body = body  # fall back; still safe since text already substituted
            return body, logged_body

        # ---- 2. Body params table ----------------------------------------
        if self.body_param_ids:
            body = {}
            logged_body = {}
            for param in self.body_param_ids.sorted('sequence'):
                actual = param.resolve_value()
                body[param.key] = actual
                if (
                    param.value_type == 'credential'
                    and param.credential_field in _SECRET_CREDENTIAL_FIELDS
                ):
                    logged_body[param.key] = '***REDACTED***'
                else:
                    logged_body[param.key] = actual
            return body, logged_body

        # ---- 3. Default body --------------------------------------------
        if self.auth_type == 'basic':
            body = {
                'username': credentials['username'],
                'password': credentials['password'],
            }
            logged_body = {
                'username': credentials['username'],
                'password': '***REDACTED***',
            }
        else:  # oauth2
            body = {
                'grant_type': 'client_credentials',
                'client_id': credentials['client_id'],
                'client_secret': credentials['client_secret'],
            }
            logged_body = {
                'grant_type': 'client_credentials',
                'client_id': credentials['client_id'],
                'client_secret': '***REDACTED***',
            }
        return body, logged_body

    # ------------------------------------------------------------------ #
    # Core reusable authentication method                                  #
    # ------------------------------------------------------------------ #

    def _authenticate(
        self,
        call_name='Authentication',
        caller_model=None,
        caller_res_id=None,
    ):
        """Perform the configured authentication handshake.

        This is the primary reusable entry-point for other models.  Any
        model that holds a Many2one reference to ``wf.service.platform``
        can call this method to obtain a valid token before making
        downstream API calls::

            result = self.service_platform_id._authenticate(
                caller_model=self._name,
                caller_res_id=self.id,
            )
            token = result['token']   # str — bearer / access token
            raw   = result['raw']     # dict — full parsed response

        The call is fully logged to ``wf.api.call.log`` regardless of
        whether it succeeds or fails.

        Parameters
        ----------
        call_name : str
            Label for this call written into the API call log.
        caller_model : str | None
            Technical name of the Odoo model whose record is initiating
            this call.  Written to the log's ``trigger_model_id``.
        caller_res_id : int | None
            ID of the caller's record.  Written to the log's
            ``trigger_res_id``.

        Returns
        -------
        dict
            ``token`` (str)           — the access / session token
            ``expires_in`` (int|None) — seconds until expiry (OAuth 2.0)
            ``raw`` (dict)            — full parsed JSON response body

        Raises
        ------
        :class:`~odoo.exceptions.UserError`
            If the endpoint is not configured, the request fails, the
            response is not valid JSON, or the JSON override is malformed.
        """
        self.ensure_one()

        endpoint = (self.auth_endpoint or '').strip()
        if not endpoint:
            raise UserError(
                _('No authentication endpoint configured for "%s".') % self.name
            )

        credentials = self._credential_map()

        # ---- build headers & body ----------------------------------------
        request_headers = self._build_request_headers(credentials)
        body, logged_body = self._build_request_body(credentials)

        # ---- fire the request --------------------------------------------
        _logger.info(
            'wf.service.platform "%s" (%s) — authenticating against %s',
            self.name, self.auth_type, endpoint,
        )

        t_start = _time.time()
        response = None
        error_message = None
        state = 'success'

        try:
            if self.body_format == 'form':
                # Form-encoded: requests sends Content-Type: application/x-www-form-urlencoded
                # and URL-encodes the dict automatically via the `data` kwarg.
                response = requests.post(
                    endpoint,
                    data=body,
                    timeout=30,
                    headers=request_headers,
                )
            else:
                # JSON (default): serialises body as JSON.
                response = requests.post(
                    endpoint,
                    json=body,
                    timeout=30,
                    headers=request_headers,
                )
            response.raise_for_status()
        except RequestException as exc:
            state = 'error'
            error_message = str(exc)
            _logger.error(
                'wf.service.platform "%s" — authentication request failed: %s',
                self.name, exc,
            )

        duration_ms = int((_time.time() - t_start) * 1000)

        # ---- parse response ----------------------------------------------
        raw = {}
        response_body_text = ''
        response_body_formatted = ''
        response_status = None
        response_headers_dict = {}

        if response is not None:
            response_status = response.status_code
            response_headers_dict = dict(response.headers)
            response_body_text = response.text or ''

            # Pretty-print the response body if it is valid JSON so the
            # ace editor in the API Call Log form renders it cleanly.
            if response_body_text:
                try:
                    response_body_formatted = json.dumps(
                        json.loads(response_body_text), indent=2
                    )
                except (ValueError, TypeError):
                    # Not JSON — store as plain text
                    response_body_formatted = response_body_text

            if state == 'success':
                try:
                    raw = response.json()
                except ValueError as exc:
                    state = 'error'
                    error_message = 'Authentication response is not valid JSON: %s' % exc

        if state == 'success' and not isinstance(raw, dict):
            state = 'error'
            error_message = 'Unexpected response format (not a JSON object).'

        # ---- write API call log ------------------------------------------
        self.env['wf.api.call.log']._create_log(
            name=call_name,
            endpoint=endpoint,
            http_method='POST',
            request_headers=json.dumps(_redact_headers(request_headers), indent=2),
            request_body=json.dumps(logged_body, indent=2),
            response_status_code=response_status,
            response_headers=json.dumps(
                _redact_headers(response_headers_dict), indent=2
            ) if response_headers_dict else None,
            response_body=(response_body_formatted or response_body_text)[:65536],
            state=state,
            error_message=error_message,
            duration_ms=duration_ms,
            service_platform_id=self.id,
            trigger_model=caller_model,
            trigger_res_id=caller_res_id,
        )

        # ---- surface errors after logging --------------------------------
        if state == 'error':
            raise UserError(
                _('Authentication failed for "%s": %s') % (self.name, error_message)
            )

        # ---- extract token -----------------------------------------------
        token = ''
        expires_in = None

        # 1. Honour the user-configured Response API Key (supports dot-path)
        if (self.response_token_key or '').strip():
            token = self._resolve_key_path(raw, self.response_token_key.strip()) or ''
            # expires_in is still probed from the top level regardless
            expires_in = raw.get('expires_in')

        # 2. Fall back to auth-type aware detection
        if not token:
            if self.auth_type == 'oauth2':
                token = raw.get('access_token') or ''
                expires_in = raw.get('expires_in')
            else:
                for key in _TOKEN_KEYS:
                    val = raw.get(key)
                    if val and isinstance(val, str):
                        token = val
                        break
                # Last resort — first non-empty string value in the response
                if not token:
                    for val in raw.values():
                        if isinstance(val, str) and val:
                            token = val
                            break

        # ---- cache token on this record ----------------------------------
        now = fields.Datetime.now()
        expiry = None
        if expires_in:
            try:
                expiry = now + datetime.timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                pass

        self.sudo().write({
            'last_token': (token or '')[:1024] or False,
            'last_authenticated': now,
            'last_token_expiry': expiry,
        })

        _logger.info(
            'wf.service.platform "%s" — authentication successful in %d ms%s',
            self.name,
            duration_ms,
            (' (token expires in %s s)' % expires_in) if expires_in else '',
        )

        return {
            'token': token,
            'expires_in': expires_in,
            'raw': raw,
        }

    def _get_token(self, call_name='Authentication', caller_model=None, caller_res_id=None):
        """Return a valid bearer token, re-authenticating only when the cache has expired.

        Preferred entry-point for Workflow API Call steps — avoids redundant
        authentication round-trips when multiple steps in the same run use
        the same platform.

        * Cached token is reused when ``last_token`` is set **and** either
          ``last_token_expiry`` is unset (non-expiring token) or still in the
          future.
        * Otherwise :meth:`_authenticate` is called for a fresh token.

        For ad-hoc testing always call :meth:`_authenticate` directly.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        if self.last_token and (
            not self.last_token_expiry or self.last_token_expiry > now
        ):
            _logger.debug(
                'wf.service.platform "%s" — reusing cached token (expiry: %s)',
                self.name,
                self.last_token_expiry or 'none',
            )
            return self.last_token
        result = self._authenticate(
            call_name=call_name,
            caller_model=caller_model,
            caller_res_id=caller_res_id,
        )
        return result.get('token') or ''

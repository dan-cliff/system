import base64
import binascii
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..models.postmark_api import (
    EVENTS_WEBHOOK_PATH, INBOUND_WEBHOOK_PATH, PARAM_ENABLED, PARAM_WEBHOOK_PASSWORD,
    PARAM_WEBHOOK_USER,
)

_logger = logging.getLogger(__name__)


class PostmarkWebhookController(http.Controller):
    """Receives Postmark's inbound email and bounce / spam complaint webhooks.

    Postmark authenticates with HTTP basic auth, using the credentials
    "Sync with Postmark" registered for the webhooks.
    """

    def _postmark_check_request(self):
        ICP = request.env['ir.config_parameter'].sudo()
        if not ICP.get_param(PARAM_ENABLED):
            return request.make_json_response({'error': 'Postmark is not enabled'}, status=403)
        user = ICP.get_param(PARAM_WEBHOOK_USER)
        password = ICP.get_param(PARAM_WEBHOOK_PASSWORD)
        header = request.httprequest.headers.get('Authorization') or ''
        scheme, _sep, encoded = header.partition(' ')
        try:
            given = base64.b64decode(encoded, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            given = ''
        expected = f'{user}:{password}'
        if not (user and password and scheme.lower() == 'basic'
                and hmac.compare_digest(given.encode(), expected.encode())):
            return request.make_json_response(
                {'error': 'Unauthorized'}, status=401,
                headers=[('WWW-Authenticate', 'Basic realm="postmark"')])
        return None

    def _postmark_payload(self):
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    @http.route(INBOUND_WEBHOOK_PATH, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def postmark_inbound(self, **kwargs):
        if (error := self._postmark_check_request()) is not None:
            return error
        payload = self._postmark_payload()
        if payload is None:
            return request.make_json_response({'error': 'Invalid JSON'}, status=400)
        request.update_env(user=SUPERUSER_ID)
        log = request.env['postmark.email.log']._postmark_receive_inbound(payload)
        # Always 200 once logged: failures are kept on the log with the
        # payload so they can be processed again from Odoo.
        return request.make_json_response({'log_id': log.id, 'state': log.state})

    @http.route(EVENTS_WEBHOOK_PATH, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def postmark_events(self, **kwargs):
        if (error := self._postmark_check_request()) is not None:
            return error
        payload = self._postmark_payload()
        if payload is None:
            return request.make_json_response({'error': 'Invalid JSON'}, status=400)
        request.update_env(user=SUPERUSER_ID)
        log = request.env['postmark.email.log']._postmark_receive_event(payload)
        return request.make_json_response({'log_id': log.id if log else False})

import hmac
import json
import logging

from odoo import http
from odoo.http import request

from ..models.mandrill_api import mandrill_signature
from ..models.mandrill_service import EVENTS_PATH, INBOUND_PATH

_logger = logging.getLogger(__name__)


class MandrillWebhookController(http.Controller):
    """Endpoints Mailchimp Transactional posts to. Mandrill checks a URL with a
    HEAD request before saving it, then POSTs a ``mandrill_events`` form field
    holding a JSON list of events."""

    @http.route(INBOUND_PATH, type='http', auth='public', methods=['GET', 'HEAD', 'POST'], csrf=False, save_session=False)
    def mandrill_inbound(self, **post):
        return self._handle(post, INBOUND_PATH, 'inbound_webhook_key', '_receive_inbound_events')

    @http.route(EVENTS_PATH, type='http', auth='public', methods=['GET', 'HEAD', 'POST'], csrf=False, save_session=False)
    def mandrill_events(self, **post):
        return self._handle(post, EVENTS_PATH, 'events_webhook_key', '_process_events')

    def _handle(self, post, path, key_param, method):
        if request.httprequest.method != 'POST':
            return request.make_response('OK')
        service = request.env['mandrill.service'].sudo()
        if not service._is_enabled():
            return request.make_response('Mailchimp Transactional is not enabled', status=404)

        key = (service._get_param(key_param) or '').strip()
        if key and not self._valid_signature(key, service._get_url(path), post):
            _logger.warning("Mailchimp Transactional: rejected %s webhook with an invalid signature", path)
            return request.make_response('Invalid signature', status=403)

        try:
            events = json.loads(post.get('mandrill_events') or '[]')
        except ValueError:
            return request.make_response('Invalid payload', status=400)
        if not isinstance(events, list):
            return request.make_response('Invalid payload', status=400)
        getattr(service, method)(events)
        return request.make_response('OK')

    @staticmethod
    def _valid_signature(key, url, post):
        received = request.httprequest.headers.get('X-Mandrill-Signature', '')
        # Mandrill signs the exact URL it was given; accept the URL as seen by
        # this request too, in case web.base.url differs (e.g. behind a proxy).
        urls = {url, request.httprequest.url}
        return any(hmac.compare_digest(received, mandrill_signature(key, u, post)) for u in urls)

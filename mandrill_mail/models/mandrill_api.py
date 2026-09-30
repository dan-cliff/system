import base64
import hashlib
import hmac
import logging

import requests

_logger = logging.getLogger(__name__)

MANDRILL_API_URL = 'https://mandrillapp.com/api/1.0/'
MANDRILL_REQUEST_TIMEOUT = 20


class MandrillError(Exception):
    """Raised when the Mailchimp Transactional API can't be reached or
    answers with an error. ``name`` is Mandrill's error name (e.g.
    ``Invalid_Key``, ``Unknown_InboundRoute``) when it gave one."""

    def __init__(self, message, name=None):
        super().__init__(message)
        self.name = name


class MandrillAPI:
    """Minimal client for the Mailchimp Transactional (Mandrill) API.

    Every call is a JSON POST to ``<endpoint>`` with the API key in the body,
    see https://mailchimp.com/developer/transactional/api/.
    """

    def __init__(self, api_key):
        self.api_key = api_key

    def call(self, endpoint, **params):
        payload = dict(params, key=self.api_key)
        try:
            response = requests.post(
                MANDRILL_API_URL + endpoint, json=payload, timeout=MANDRILL_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise MandrillError(f'{e.__class__.__name__}: {e}') from e
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code != 200:
            if isinstance(data, dict) and data.get('status') == 'error':
                raise MandrillError(data.get('message') or response.text, name=data.get('name'))
            raise MandrillError(f'HTTP {response.status_code}: {response.text[:500]}')
        return data

    # users
    def ping(self):
        return self.call('users/ping2')

    # messages
    def send_raw(self, raw_message, from_email=None, from_name=None, to=None, **params):
        if from_email:
            params['from_email'] = from_email
        if from_name:
            params['from_name'] = from_name
        if to:
            params['to'] = to
        return self.call('messages/send-raw', raw_message=raw_message, **params)

    # inbound
    def inbound_domains(self):
        return self.call('inbound/domains')

    def add_inbound_domain(self, domain):
        return self.call('inbound/add-domain', domain=domain)

    def check_inbound_domain(self, domain):
        return self.call('inbound/check-domain', domain=domain)

    def inbound_routes(self, domain):
        return self.call('inbound/routes', domain=domain)

    def add_inbound_route(self, domain, pattern, url):
        return self.call('inbound/add-route', domain=domain, pattern=pattern, url=url)

    def update_inbound_route(self, route_id, pattern, url):
        return self.call('inbound/update-route', id=route_id, pattern=pattern, url=url)

    def delete_inbound_route(self, route_id):
        return self.call('inbound/delete-route', id=route_id)

    # webhooks (message events)
    def webhooks(self):
        return self.call('webhooks/list')

    def add_webhook(self, url, events, description=None):
        return self.call('webhooks/add', url=url, events=events, description=description or '')

    def update_webhook(self, webhook_id, url, events, description=None):
        return self.call('webhooks/update', id=webhook_id, url=url, events=events,
                         description=description or '')


def mandrill_signature(key, url, params):
    """Signature Mandrill puts in ``X-Mandrill-Signature``: base64 of the
    HMAC-SHA1 of the webhook URL followed by every POST key and value,
    sorted by key."""
    signed = url + ''.join(f'{k}{params[k]}' for k in sorted(params))
    digest = hmac.new(key.encode(), signed.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()

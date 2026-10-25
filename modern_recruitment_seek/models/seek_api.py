# -*- coding: utf-8 -*-
"""SEEK API client (https://developer.seek.com).

SEEK's API is GraphQL. Partner tokens come from SEEK's OAuth endpoint with
the integration's client credentials and are cached until shortly before
they expire.
"""
import logging
import time
import uuid

import requests

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SEEK_GRAPHQL_URL = 'https://graphql.seek.com/graphql'
SEEK_AUTH_URL = 'https://auth.seek.com/oauth/token'
SEEK_SCHEME = 'seekAnz'
TIMEOUT = 30
# (database, client id) -> (token, expiry timestamp)
_TOKENS = {}


class TalentSeekApi(models.AbstractModel):
    _name = 'talent.seek.api'
    _description = 'SEEK API'

    @api.model
    def _seek_company(self, company=None):
        company = (company or self.env.company).sudo()
        if not (company.seek_client_id and company.seek_client_secret and company.seek_hirer_id):
            raise UserError(self.env._(
                'Connect SEEK first: enter the Client ID, Client Secret and Hirer ID in '
                'Settings › Talent › Job Boards › SEEK.'))
        return company

    @api.model
    def _seek_token(self, company=None):
        company = self._seek_company(company)
        key = (self.env.cr.dbname, company.seek_client_id)
        token, expiry = _TOKENS.get(key, (None, 0))
        if token and expiry > time.time() + 60:
            return token
        try:
            response = requests.post(SEEK_AUTH_URL, json={
                'client_id': company.seek_client_id,
                'client_secret': company.seek_client_secret,
                'grant_type': 'client_credentials',
                'audience': 'https://graphql.seek.com',
            }, headers={'User-Agent': self._seek_user_agent()}, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            _logger.info('SEEK authentication failed: %s', error)
            raise UserError(self.env._('SEEK refused the credentials: %s', error)) from error
        token = data['access_token']
        _TOKENS[key] = (token, time.time() + int(data.get('expires_in') or 3600))
        return token

    @api.model
    def _seek_user_agent(self):
        return 'odoo-talent/19.0'

    @api.model
    def _seek_query(self, query, variables=None, company=None):
        """Run a GraphQL query or mutation; returns its data, raises on errors."""
        token = self._seek_token(company)
        try:
            response = requests.post(SEEK_GRAPHQL_URL, json={'query': query, 'variables': variables or {}}, headers={
                'Authorization': 'Bearer %s' % token,
                'User-Agent': self._seek_user_agent(),
                'X-Request-Id': str(uuid.uuid4()),
                'Accept-Language': 'en-AU',
            }, timeout=TIMEOUT)
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise UserError(self.env._('SEEK could not be reached: %s', error)) from error
        if payload.get('errors'):
            messages = '\n'.join(error.get('message', '') for error in payload['errors'])
            _logger.info('SEEK API error: %s', messages)
            raise UserError(self.env._('SEEK returned an error:\n%s', messages))
        if response.status_code >= 400:
            raise UserError(self.env._('SEEK returned HTTP %s.', response.status_code))
        return payload.get('data') or {}

    @api.model
    def _seek_download(self, url, company=None):
        """A SEEK attachment (résumé, cover letter): (content, mimetype)."""
        response = requests.get(url, headers={
            'Authorization': 'Bearer %s' % self._seek_token(company),
            'User-Agent': self._seek_user_agent(),
        }, timeout=TIMEOUT)
        response.raise_for_status()
        return response.content, response.headers.get('Content-Type', 'application/octet-stream').split(';')[0]

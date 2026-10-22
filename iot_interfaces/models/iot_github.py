# -*- coding: utf-8 -*-
import requests

from odoo import _, api, models
from odoo.exceptions import UserError

from .iot_program import GITHUB_API, GITHUB_TIMEOUT

PARAM_ENABLED = 'iot_interfaces.github_enabled'
PARAM_TOKEN = 'iot_interfaces.github_token'


class IotGithub(models.AbstractModel):
    """Calls to the GitHub REST API with the token set in Settings."""
    _name = 'iot.github'
    _description = 'IoT Interfaces GitHub Connection'

    @api.model
    def _enabled(self):
        params = self.env['ir.config_parameter'].sudo()
        return bool(params.get_param(PARAM_ENABLED)) and bool(params.get_param(PARAM_TOKEN))

    @api.model
    def _request(self, method, path, payload=None, params=None, allow_missing=False):
        token = self.env['ir.config_parameter'].sudo().get_param(PARAM_TOKEN)
        if not token:
            raise UserError(_('Set the GitHub access token in IoT Interfaces > Configuration > Settings.'))
        try:
            response = requests.request(method, GITHUB_API + path, json=payload, params=params,
                                        timeout=GITHUB_TIMEOUT, headers={
                                            'Authorization': 'Bearer %s' % token,
                                            'Accept': 'application/vnd.github+json',
                                            'X-GitHub-Api-Version': '2022-11-28',
                                        })
        except requests.RequestException as error:
            raise UserError(_('GitHub could not be reached: %s', error))
        if allow_missing and response.status_code in (404, 409):
            return None
        if response.status_code >= 400:
            try:
                message = response.json().get('message')
            except ValueError:
                message = response.text[:200]
            raise UserError(_('GitHub refused %(method)s %(path)s: %(status)s %(message)s',
                              method=method, path=path, status=response.status_code, message=message))
        return response.json() if response.content else {}

    @api.model
    def _get(self, path, params=None, allow_missing=False):
        return self._request('GET', path, params=params, allow_missing=allow_missing)

    @api.model
    def _post(self, path, payload):
        return self._request('POST', path, payload)

    @api.model
    def _patch(self, path, payload):
        return self._request('PATCH', path, payload)

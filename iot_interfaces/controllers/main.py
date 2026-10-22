# -*- coding: utf-8 -*-
"""IoT Interfaces HTTP API, shared by every Node role.

Routes:
    GET  /iot/install.sh                  Builds a Node: agent, pairing, program (no key needed)
    GET  /iot/pi/iot_node_agent.py        The Node agent (no key needed)
    GET  /iot/pi/iot_auth.py              The signing library (no key needed)
    POST /iot/v1/pair                     Swap a one-time pairing code for the Node's id and key
    POST /iot/v1/hello                    Signed check-in: online status, rolling key, program updates
    GET  /iot/v1/program/file/<id>        Signed download of a program file for an update

Apps add their own signed routes and check them with ``authenticate``:

    from odoo.addons.iot_interfaces.controllers.main import authenticate

    node, error = authenticate(roles=['my_role'])
    if error:
        return error
"""
import base64
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import file_open

_logger = logging.getLogger(__name__)


def json_response(data, status=200):
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        status=status,
    )


def error_response(message, status=400):
    return json_response({'status': 'error', 'message': message}, status=status)


def json_body():
    """The request's JSON object body, or None."""
    try:
        data = json.loads(request.httprequest.get_data(cache=True, as_text=True) or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def node_env():
    """Environment for work done on a Node's behalf: superuser (posts as
    OdooBot), flagged so records can tell nobody in Odoo did it."""
    return request.env(user=SUPERUSER_ID, context=dict(request.env.context, iot_node=True))


def authenticate(roles=None):
    """The Node that signed this request, or (None, a 401 response)."""
    node, reason = node_env()['iot.node']._iot_authenticate(request.httprequest, roles=roles)
    if not node:
        return None, error_response(reason, 401)
    return node, None


# Files anyone may download: they hold no settings or keys.
NODE_FILES = {
    '/iot/install.sh': ('iot_interfaces/node/install.sh', 'text/x-shellscript'),
    '/iot/pi/iot_node_agent.py': ('iot_interfaces/node/iot_node_agent.py', 'text/x-python'),
    '/iot/pi/iot_auth.py': ('iot_interfaces/lib/iot_auth.py', 'text/x-python'),
}


class IotController(http.Controller):

    @http.route(list(NODE_FILES), type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def node_file(self, **kwargs):
        path, content_type = NODE_FILES[request.httprequest.path]
        with file_open(path, 'rb') as file:
            data = file.read()
        return request.make_response(data, headers=[
            ('Content-Type', '%s; charset=utf-8' % content_type),
            ('Cache-Control', 'no-cache'),
        ])

    @http.route('/iot/v1/pair', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def pair(self, **kwargs):
        data = json_body()
        if data is None:
            return error_response('The request body must be a JSON object.')
        try:
            with request.env.cr.savepoint():
                node, secret = node_env()['iot.node']._iot_pair(
                    str(data.get('code') or ''), data.get('role'), data.get('mac'), data.get('macs'),
                    data.get('hostname'))
        except UserError as error:
            return error_response(error.args[0], 403)
        _logger.info('IoT Node %s (%s) paired as %s', node.id, node.name, node.role)
        return json_response({'status': 'ok', 'node': node.node_key, 'secret': secret,
                              'name': node.name, 'role': node.role})

    @http.route('/iot/v1/hello', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def hello(self, **kwargs):
        node, error = authenticate()
        if error:
            return error
        data = json_body() or {}
        node._iot_heartbeat(request.httprequest.remote_addr, str(data.get('version') or ''))
        if 'program' in data:
            node._iot_report_program(data['program'])
        result = dict(node._iot_hello_data(), status='ok', name=node.name, role=node.role,
                      program=node._iot_program_payload())
        new_secret = node._iot_new_secret()
        if new_secret:
            result['new_secret'] = new_secret
        return json_response(result)

    @http.route('/iot/v1/program/file/<int:file_id>', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def program_file(self, file_id, **kwargs):
        node, error = authenticate()
        if error:
            return error
        file = node.env['iot.program.file'].browse(file_id).exists()
        if not file or file.version_id.state != 'released' or file.version_id.role != node.role:
            return error_response('Not found.', 404)
        return request.make_response(base64.b64decode(file.with_context(bin_size=False).data or b''), headers=[
            ('Content-Type', 'application/octet-stream'),
            ('Cache-Control', 'no-store'),
        ])

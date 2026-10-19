# -*- coding: utf-8 -*-
"""HTTP API the Embroidery Bridge uses. Requests are signed with the key
the bridge got when it was paired (see lib/device_auth.py).

Routes:
    GET  /embroidery/bridge/install.sh                 Raspberry Pi installer (no key needed)
    GET  /embroidery/bridge/embroidery_bridge.py       The bridge program (no key needed)
    POST /embroidery/bridge/v1/poll                    Heartbeat; returns machines and queued stitch outs
    GET  /embroidery/bridge/v1/stitchout/<id>/file     The stitch out's .pes file
    POST /embroidery/bridge/v1/stitchout/<id>/report   Progress / status / errors for a stitch out
"""
import base64
import json
import logging

from odoo import SUPERUSER_ID, fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

API_VERSION = 2
POLL_SECONDS_IDLE = 15
POLL_SECONDS_ACTIVE = 5

# Program files anyone may download: they hold no settings or keys.
PI_FILES = {
    '/embroidery/bridge/install.sh': ('embroidery_jobbing/bridge/install.sh', 'text/x-shellscript'),
    '/embroidery/bridge/embroidery_bridge.py': ('embroidery_jobbing/bridge/embroidery_bridge.py', 'text/x-python'),
    '/embroidery/display/install.sh': ('embroidery_jobbing/display/install.sh', 'text/x-shellscript'),
    '/embroidery/display/embroidery_display.py': ('embroidery_jobbing/display/embroidery_display.py', 'text/x-python'),
    '/embroidery/pi/embroidery_auth.py': ('embroidery_jobbing/lib/device_auth.py', 'text/x-python'),
}


def _json(data, status=200):
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        status=status,
    )


def _error(message, status=400):
    return _json({'status': 'error', 'message': message}, status=status)


def _body():
    try:
        data = json.loads(request.httprequest.get_data(cache=True, as_text=True) or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def authenticate(model):
    """The device that signed the request (sudo, flagged as a device
    context), or (None, error response)."""
    env = request.env(user=SUPERUSER_ID, context=dict(request.env.context, embroidery_bridge=True))
    device, reason = env[model]._auth_request(request.httprequest)
    if not device:
        return None, _error(reason, 401)
    return device, None


def _bridge_stitchout(bridge, stitchout_id):
    stitchout = bridge.env['embroidery.stitchout'].browse(stitchout_id).exists()
    if not stitchout or stitchout.machine_id.bridge_id != bridge:
        return None
    return stitchout


class EmbroideryPiController(http.Controller):

    @http.route(list(PI_FILES), type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def pi_file(self, **kwargs):
        path, content_type = PI_FILES[request.httprequest.path]
        with file_open(path, 'rb') as file:
            data = file.read()
        return request.make_response(data, headers=[
            ('Content-Type', '%s; charset=utf-8' % content_type),
            ('Cache-Control', 'no-cache'),
        ])

    @http.route('/embroidery/pi/v1/pair', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def pair(self, **kwargs):
        """Swap a one-time pairing code for the Pi's device id and key."""
        data = _body()
        if data is None:
            return _error('The request body must be a JSON object.')
        model = {'bridge': 'embroidery.bridge', 'display': 'embroidery.display'}.get(data.get('kind'))
        if not model:
            return _error('Unknown kind of Raspberry Pi.')
        try:
            with request.env.cr.savepoint():
                device, secret = request.env[model]._auth_pair(
                    str(data.get('code') or ''), data.get('mac'), data.get('macs'), data.get('hostname'))
        except UserError as error:
            return _error(error.args[0], 403)
        _logger.info('Raspberry Pi paired as %s %s (%s)', data.get('kind'), device.id, device.display_name)
        return _json({'status': 'ok', 'device': device.device_key, 'secret': secret, 'name': device.display_name})


class EmbroideryBridgeController(http.Controller):

    @http.route('/embroidery/bridge/v1/poll', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def poll(self, **kwargs):
        bridge, error = authenticate('embroidery.bridge')
        if error:
            return error
        data = _body()
        if data is None:
            return _error('The request body must be a JSON object.')

        bridge.write({
            'last_seen': fields.Datetime.now(),
            'last_ip': request.httprequest.remote_addr,
            'bridge_version': str(data.get('version') or '')[:32],
        })
        machines = bridge.machine_ids.filtered('active')
        reported = {m.get('id'): m for m in data.get('machines') or [] if isinstance(m, dict)}
        for machine in machines:
            status = reported.get(machine.id)
            values = {
                'bridge_reported_online': bool(status and status.get('online')),
                'bridge_message': str((status or {}).get('message') or '')[:256] or False,
            }
            if any(machine[key] != value for key, value in values.items()):
                machine.write(values)

        stitchouts = bridge.env['embroidery.stitchout'].search(
            [('machine_id', 'in', machines.ids), ('state', 'in', bridge.env['embroidery.stitchout']._OPEN_STATES)],
            order='id',
        )
        queued = stitchouts.filtered(lambda s: s.state == 'queued')
        result = {
            'status': 'ok',
            'api_version': API_VERSION,
            'bridge': bridge.name,
            'poll_seconds': POLL_SECONDS_ACTIVE if stitchouts else POLL_SECONDS_IDLE,
            'machines': [m._bridge_config() for m in machines],
            'queued': [s._bridge_job() for s in queued],
            # Stitch outs the bridge should still be looking after; any other
            # it is running was finished or cancelled in Odoo.
            'open': {str(s.id): s.state for s in stitchouts},
        }
        new_secret = bridge._auth_new_secret()
        if new_secret:
            result['new_secret'] = new_secret
        return _json(result)

    @http.route('/embroidery/bridge/v1/stitchout/<int:stitchout_id>/file', type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def stitchout_file(self, stitchout_id, **kwargs):
        bridge, error = authenticate('embroidery.bridge')
        if error:
            return error
        stitchout = _bridge_stitchout(bridge, stitchout_id)
        if not stitchout:
            return _error('Stitch out not found.', 404)
        design = stitchout.design_id.with_context(bin_size=False)
        data = base64.b64decode(design.design_file or b'')
        filename = (design.design_filename or '%s.pes' % design.name).replace('"', '')
        return request.make_response(data, headers=[
            ('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ('Cache-Control', 'no-store'),
        ])

    @http.route('/embroidery/bridge/v1/stitchout/<int:stitchout_id>/report', type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def stitchout_report(self, stitchout_id, **kwargs):
        bridge, error = authenticate('embroidery.bridge')
        if error:
            return error
        stitchout = _bridge_stitchout(bridge, stitchout_id)
        if not stitchout:
            return _error('Stitch out not found.', 404)
        data = _body()
        if data is None:
            return _error('The request body must be a JSON object.')
        stitchout._apply_report(data)
        return _json({'status': 'ok', 'state': stitchout.state})

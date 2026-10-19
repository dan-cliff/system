# -*- coding: utf-8 -*-
"""HTTP API the Embroidery Bridge uses. Every request carries the bridge's
access token as ``Authorization: Bearer <token>``.

Routes:
    POST /embroidery/bridge/v1/poll                    Heartbeat; returns machines and queued stitch outs
    GET  /embroidery/bridge/v1/stitchout/<id>/file     The stitch out's .pes file
    POST /embroidery/bridge/v1/stitchout/<id>/report   Progress / status / errors for a stitch out
"""
import base64
import json
import logging

from odoo import SUPERUSER_ID, fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

API_VERSION = 1
POLL_SECONDS_IDLE = 15
POLL_SECONDS_ACTIVE = 5


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
        data = json.loads(request.httprequest.get_data(as_text=True) or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _bridge():
    """The bridge making the request (as superuser), or None."""
    header = request.httprequest.headers.get('Authorization', '')
    token = header[7:].strip() if header.lower().startswith('bearer ') else ''
    env = request.env(user=SUPERUSER_ID, context=dict(request.env.context, embroidery_bridge=True))
    bridge = env['embroidery.bridge']._authenticate(token)
    return bridge or None


def _bridge_stitchout(bridge, stitchout_id):
    stitchout = bridge.env['embroidery.stitchout'].browse(stitchout_id).exists()
    if not stitchout or stitchout.machine_id.bridge_id != bridge:
        return None
    return stitchout


class EmbroideryBridgeController(http.Controller):

    @http.route('/embroidery/bridge/v1/poll', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def poll(self, **kwargs):
        bridge = _bridge()
        if not bridge:
            return _error('Unknown or missing access token.', 401)
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
        return _json({
            'status': 'ok',
            'api_version': API_VERSION,
            'bridge': bridge.name,
            'poll_seconds': POLL_SECONDS_ACTIVE if stitchouts else POLL_SECONDS_IDLE,
            'machines': [m._bridge_config() for m in machines],
            'queued': [s._bridge_job() for s in queued],
            # Stitch outs the bridge should still be looking after; any other
            # it is running was finished or cancelled in Odoo.
            'open': {str(s.id): s.state for s in stitchouts},
        })

    @http.route('/embroidery/bridge/v1/stitchout/<int:stitchout_id>/file', type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def stitchout_file(self, stitchout_id, **kwargs):
        bridge = _bridge()
        if not bridge:
            return _error('Unknown or missing access token.', 401)
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
        bridge = _bridge()
        if not bridge:
            return _error('Unknown or missing access token.', 401)
        stitchout = _bridge_stitchout(bridge, stitchout_id)
        if not stitchout:
            return _error('Stitch out not found.', 404)
        data = _body()
        if data is None:
            return _error('The request body must be a JSON object.')
        stitchout._apply_report(data)
        return _json({'status': 'ok', 'state': stitchout.state})

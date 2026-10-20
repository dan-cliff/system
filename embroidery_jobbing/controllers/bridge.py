# -*- coding: utf-8 -*-
"""HTTP API of the Embroidery Bridge Node role. Requests come from the Node
agent, signed with the Node's rolling key (IoT Interfaces).

Routes:
    POST /embroidery/bridge/v1/poll                    Machines and queued stitch outs
    GET  /embroidery/bridge/v1/stitchout/<id>/file     The stitch out's .pes file
    POST /embroidery/bridge/v1/stitchout/<id>/report   Progress / status / errors for a stitch out
"""
import base64

from odoo import http
from odoo.http import request

from odoo.addons.iot_interfaces.controllers.main import authenticate, error_response, json_body, json_response

from ..models.iot_node import ROLE_BRIDGE

API_VERSION = 3
POLL_SECONDS_IDLE = 15
POLL_SECONDS_ACTIVE = 5


def _bridge_stitchout(bridge, stitchout_id):
    stitchout = bridge.env['embroidery.stitchout'].browse(stitchout_id).exists()
    if not stitchout or stitchout.machine_id.bridge_id != bridge:
        return None
    return stitchout


class EmbroideryBridgeController(http.Controller):

    @http.route('/embroidery/bridge/v1/poll', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def poll(self, **kwargs):
        bridge, error = authenticate(roles=[ROLE_BRIDGE])
        if error:
            return error
        data = json_body()
        if data is None:
            return error_response('The request body must be a JSON object.')
        bridge._iot_heartbeat(request.httprequest.remote_addr)
        machines = bridge.embroidery_machine_ids.filtered('active')
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
        return json_response({
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
        bridge, error = authenticate(roles=[ROLE_BRIDGE])
        if error:
            return error
        stitchout = _bridge_stitchout(bridge, stitchout_id)
        if not stitchout:
            return error_response('Stitch out not found.', 404)
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
        bridge, error = authenticate(roles=[ROLE_BRIDGE])
        if error:
            return error
        stitchout = _bridge_stitchout(bridge, stitchout_id)
        if not stitchout:
            return error_response('Stitch out not found.', 404)
        data = json_body()
        if data is None:
            return error_response('The request body must be a JSON object.')
        stitchout._apply_report(data)
        return json_response({'status': 'ok', 'state': stitchout.state})

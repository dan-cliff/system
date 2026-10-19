# -*- coding: utf-8 -*-
"""Machine status page for wall displays (a Raspberry Pi plugged into a TV).

The Pi's display agent serves the page to Chromium on the Pi itself and
forwards its requests here, signed with the Pi's key (see
lib/device_auth.py), so the screen needs no login and no secret address.

Routes:
    GET  /embroidery/pi/v1/display/page          The status page
    GET  /embroidery/pi/v1/display/data.json     What the page shows (polled)
    GET  /embroidery/pi/v1/display/design/<id>   Preview of a design on one of the board's machines
    POST /embroidery/pi/v1/display/hello         Agent heartbeat (hands out new keys)
    GET  /embroidery/board/<id>/preview          The page for a logged-in user
    GET  /embroidery/board/<id>/preview/data.json
"""
import base64

from odoo import http
from odoo.http import request

from .bridge import _body, _error, _json, authenticate

PAGE_VERSION = '3'


def _page(data_url, title):
    return request.render('embroidery_jobbing.status_page', {
        'data_url': data_url,
        'title': title,
        'version': PAGE_VERSION,
    })


class EmbroideryDisplayController(http.Controller):

    # ── Raspberry Pi display (signed requests) ────────────────────────────
    @http.route('/embroidery/pi/v1/display/page', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display_page(self, **kwargs):
        display, error = authenticate('embroidery.display')
        if error:
            return error
        # The agent serves the page at / and data.json beside it.
        return _page('data.json', display.board_id.title or display.board_id.name)

    @http.route('/embroidery/pi/v1/display/data.json', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display_data(self, w=None, h=None, **kwargs):
        display, error = authenticate('embroidery.display')
        if error:
            return error
        size = '%sx%s' % (w, h) if (w or '').isdigit() and (h or '').isdigit() else None
        display._heartbeat(request.httprequest.remote_addr, size)
        data = display.board_id._display_data(
            image_url=lambda design: 'design/%s?v=%s' % (
                design.id, int(design.write_date.timestamp()) if design.write_date else 0),
            logo_url='logo.png',
        )
        data.update(status='ok', display=display.name, reload=display.reload_counter)
        return _json(data)

    @http.route('/embroidery/pi/v1/display/design/<int:design_id>', type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def display_design(self, design_id, **kwargs):
        display, error = authenticate('embroidery.display')
        if error:
            return error
        # Only the designs on the board's machines right now.
        design = display.board_id._machines().current_stitchout_id.design_id.filtered(lambda d: d.id == design_id)
        if not design or not design.image_256:
            return _error('Not found.', 404)
        return request.make_response(base64.b64decode(design.image_256), headers=[
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'private, max-age=86400'),
        ])

    @http.route('/embroidery/pi/v1/display/hello', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def display_hello(self, **kwargs):
        display, error = authenticate('embroidery.display')
        if error:
            return error
        data = _body() or {}
        display._heartbeat(request.httprequest.remote_addr, version=str(data.get('version') or '')[:32])
        result = {'status': 'ok', 'name': display.name, 'reload': display.reload_counter}
        new_secret = display._auth_new_secret()
        if new_secret:
            result['new_secret'] = new_secret
        return _json(result)

    # ── Preview for Odoo users ────────────────────────────────────────────
    @http.route('/embroidery/board/<int:board_id>/preview', type='http', auth='user', methods=['GET'])
    def board_preview(self, board_id, **kwargs):
        board = request.env['embroidery.status.board'].browse(board_id).exists()
        if not board:
            return request.not_found()
        return _page('/embroidery/board/%s/preview/data.json' % board.id, board.title or board.name)

    @http.route('/embroidery/board/<int:board_id>/preview/data.json', type='http', auth='user', methods=['GET'])
    def board_preview_data(self, board_id, **kwargs):
        board = request.env['embroidery.status.board'].browse(board_id).exists()
        if not board:
            return _error('Not found.', 404)
        data = board._display_data(
            image_url=lambda design: '/web/image/embroidery.design/%s/image_256' % design.id,
            logo_url='/logo.png',
        )
        data.update(status='ok', display=None, reload=0)
        return _json(data)

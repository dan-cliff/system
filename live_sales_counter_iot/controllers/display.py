"""Live Sales Counter on a Display Screen Node.

The Node's home page stays /embroidery/node/v1/display/page; when the Node
shows a live sales counter that page is the live sales page, and it polls
live_data.json next to it. Requests come signed by the Node agent
(IoT Interfaces), so private counters need no login on the screen.

Routes:
    GET  /embroidery/node/v1/display/page             The live page (when showing a counter)
    GET  /embroidery/node/v1/display/live_data.json   What the live page shows (polled)
"""
import json

from odoo import http
from odoo.http import request

from odoo.addons.embroidery_jobbing.controllers.display import EmbroideryDisplayController
from odoo.addons.embroidery_jobbing.models.iot_node import ROLE_DISPLAY
from odoo.addons.iot_interfaces.controllers.main import authenticate, json_response as _json


class LiveCounterDisplayController(EmbroideryDisplayController):

    def _display_page(self, display):
        if not display._shows_live_counter():
            return super()._display_page(display)
        counter = display.live_counter_id.sudo()
        config = counter._page_config()
        config.update(data_url='live_data.json', demo=False)
        return request.render('live_sales_counter.live_page', {
            'counter': counter,
            'config_json': json.dumps(config),
        })

    def _display_data(self, display, w=None, h=None):
        if display._shows_live_counter():
            # The status board page is still open: make it reload into the live page.
            return _json({'status': 'ok', 'reload': display.reload_counter, 'switch_page': True})
        return super()._display_data(display, w, h)

    @http.route('/embroidery/node/v1/display/live_data.json', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display_live_data(self, places=None, **kwargs):
        display, error = authenticate(roles=[ROLE_DISPLAY])
        if error:
            return error
        display._iot_heartbeat(request.httprequest.remote_addr)
        if not display._shows_live_counter():
            return _json({'status': 'ok', 'switch_page': True, 'reload': display.reload_counter})
        data = display.live_counter_id._live_data(with_places=bool(places))
        data.update(status='ok', reload=display.reload_counter)
        return _json(data)

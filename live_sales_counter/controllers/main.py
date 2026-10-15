"""The live sales page.

/live-sales/<token>       the full-screen page
/live-sales/<token>/data  JSON the page polls for new sales

Public counters work for anyone with the link. Private counters need a
signed in user with Live Sales Counter access in the counter's company.
"""
import json
from urllib.parse import quote

from odoo import _, http
from odoo.http import request


def _json(data, status=200):
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        status=status,
    )


class LiveSalesCounterController(http.Controller):

    def _not_found(self):
        return request.make_response(
            _('This live sales link is not valid. Ask your administrator for the current link.'),
            headers=[('Content-Type', 'text/plain; charset=utf-8')], status=404,
        )

    @http.route('/live-sales/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def live_page(self, token, demo=None, **kw):
        counter = request.env['live.counter']._get_by_token(token)
        if not counter:
            return self._not_found()
        user = request.env.user
        if not counter._can_view(user):
            if user._is_public():
                return request.redirect('/web/login?redirect=%s' % quote(f'/live-sales/{token}'))
            return request.make_response(
                _('You do not have access to this live sales page.'),
                headers=[('Content-Type', 'text/plain; charset=utf-8')], status=403,
            )
        config = counter._page_config()
        config.update({
            'data_url': f'/live-sales/{token}/data',
            'demo': bool(demo),
        })
        response = request.render('live_sales_counter.live_page', {
            'counter': counter,
            'config_json': json.dumps(config),
        })
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @http.route('/live-sales/<string:token>/data', type='http', auth='public', methods=['GET'], csrf=False)
    def live_data(self, token, places=None, **kw):
        counter = request.env['live.counter']._get_by_token(token)
        if not counter:
            return _json({'error': 'not_found'}, status=404)
        if not counter._can_view(request.env.user):
            return _json({'error': 'access_denied'}, status=403)
        return _json(counter._live_data(with_places=bool(places)))

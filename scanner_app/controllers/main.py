import json

from odoo import http
from odoo.http import request


class ScannerAppController(http.Controller):

    @http.route('/scanner_app/manifest.webmanifest', type='http', auth='public', csrf=False)
    def manifest(self):
        manifest = {
            'name': 'Scanner',
            'short_name': 'Scanner',
            'description': 'Scan barcodes to receive/create Purchase Orders and run Stocktakes.',
            'start_url': '/odoo/scanner',
            'scope': '/odoo',
            'display': 'standalone',
            'orientation': 'any',
            'background_color': '#37474F',
            'theme_color': '#37474F',
            'icons': [
                {'src': '/scanner_app/static/description/icon_192.png', 'sizes': '192x192', 'type': 'image/png'},
                {'src': '/scanner_app/static/description/icon_512.png', 'sizes': '512x512', 'type': 'image/png'},
                {
                    'src': '/scanner_app/static/description/icon_512_maskable.png',
                    'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable',
                },
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[('Content-Type', 'application/manifest+json')],
        )

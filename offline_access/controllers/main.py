"""Offline Access routes.

    GET  /web/manifest.webmanifest        Odoo's app manifest, branded from Settings
    GET  /web/service-worker.js           Odoo's service worker, plus app shell caching
    GET  /offline_access/icon/<size>      App icon (PNG) at 180, 192 or 512 px
    POST /offline_access/heartbeat        A signed-in browser reporting in
    POST /offline_access/device_status    Any browser asking whether it was revoked
"""
import base64

from odoo import http
from odoo.http import request
from odoo.tools.image import image_process

from odoo.addons.web.controllers.webmanifest import WebManifest

ICON_SIZES = (180, 192, 512)


class OfflineAccessWebManifest(WebManifest):

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        config = request.env['offline.access.device']._get_offline_access_config()
        if not config['enabled']:
            return manifest
        manifest.update({
            'id': '/odoo',
            'short_name': manifest['name'],
            'background_color': config['theme_color'],
            'theme_color': config['theme_color'],
        })
        if config['icon']:
            manifest['icons'] = [{
                'src': f"/offline_access/icon/{size}?v={config['icon_version']}",
                'sizes': f'{size}x{size}',
                'type': 'image/png',
                'purpose': 'any',
            } for size in (192, 512)]
        return manifest

    def _get_service_worker_content(self):
        body = super()._get_service_worker_content()
        Device = request.env['offline.access.device']
        if not Device._get_offline_access_config()['enabled']:
            return body
        return body + '\n' + Device._get_service_worker_extension()[0]


class OfflineAccessController(http.Controller):

    @http.route('/offline_access/icon/<int:size>', type='http', auth='public', methods=['GET'], readonly=True)
    def icon(self, size, **kw):
        if size not in ICON_SIZES:
            raise request.not_found()
        icon = request.env['offline.access.device']._get_offline_access_config()['icon']
        if not icon:
            return request.redirect(f"/web/static/img/odoo-icon-{'192x192' if size < 512 else '512x512'}.png")
        image = image_process(base64.b64decode(icon.datas), size=(size, size), expand=True, output_format='PNG')
        return request.make_response(image, headers=[
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'public, max-age=86400'),
        ])

    @http.route('/offline_access/heartbeat', type='jsonrpc', auth='user', methods=['POST'])
    def heartbeat(self, device_uid=None, **info):
        Device = request.env['offline.access.device'].sudo()
        user = request.env.user
        if not user._is_internal() or not Device._valid_device_uid(device_uid):
            return {'enabled': False, 'wipe': False}
        config = Device._get_offline_access_config()
        if not config['enabled']:
            return dict(Device._check_wipe(device_uid), enabled=False)
        result = Device._register_heartbeat(user, device_uid, info)
        return dict(result, enabled=True, heartbeat_minutes=config['heartbeat_minutes'])

    @http.route('/offline_access/device_status', type='jsonrpc', auth='public', methods=['POST'])
    def device_status(self, device_uid=None, **kw):
        """Lets a revoked browser find out it must wipe its data, even though
        Revoke has already signed it out. Only ever answers yes or no."""
        Device = request.env['offline.access.device'].sudo()
        if not Device._valid_device_uid(device_uid):
            return {'wipe': False}
        return Device._check_wipe(device_uid)

import base64
import io
import json
from datetime import timedelta

from PIL import Image

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

DEVICE_UID = '0f6e2c1a-7d1b-4a33-9b1e-5c2f8a6d4e10'


def make_png(size=40, color=(200, 30, 30)):
    output = io.BytesIO()
    Image.new('RGB', (size, size), color).save(output, format='PNG')
    return base64.b64encode(output.getvalue())


@tagged('post_install', '-at_install')
class TestOfflineAccess(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ICP.set_param('offline_access.enabled', True)
        cls.ICP.set_param('offline_access.theme_color', '#1f6f43')
        cls.Device = cls.env['offline.access.device']
        cls.worker = new_test_user(cls.env, login='offline_worker', password='offline_worker',
                                   groups='base.group_user')

    def rpc(self, path, **params):
        response = self.url_open(path, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn('error', body, body.get('error'))
        return body['result']

    def heartbeat(self, **info):
        params = dict(device_uid=DEVICE_UID, browser='Chrome', platform='Android', installed=True,
                      app_version='abc123', storage_used=5 * 1024 * 1024, storage_quota=1024 * 1024 * 1024)
        return self.rpc('/offline_access/heartbeat', **dict(params, **info))

    # ── Manifest, service worker, icon ───────────────────────────────────────

    def test_manifest_branded_when_enabled(self):
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifest['theme_color'], '#1f6f43')
        self.assertEqual(manifest['scope'], '/odoo')
        self.assertTrue(manifest['icons'][0]['src'].startswith('/web/static/img/'))

        self.env['res.config.settings'].create({'offline_access_icon': make_png()}).execute()
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertTrue(manifest['icons'][0]['src'].startswith('/offline_access/icon/192?v='))
        icon = self.url_open('/offline_access/icon/512')
        self.assertEqual(icon.headers['Content-Type'], 'image/png')
        self.assertEqual(Image.open(io.BytesIO(icon.content)).size, (512, 512))
        self.assertEqual(self.url_open('/offline_access/icon/77').status_code, 404)

    def test_manifest_untouched_when_disabled(self):
        self.ICP.set_param('offline_access.enabled', False)
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifest['theme_color'], '#714B67')
        service_worker = self.url_open('/web/service-worker.js').text
        self.assertNotIn('offline-access-', service_worker)

    def test_service_worker_extends_odoo(self):
        response = self.url_open('/web/service-worker.js')
        self.assertEqual(response.headers['Service-Worker-Allowed'], '/odoo')
        self.assertIn('odoo-sw-cache', response.text)  # Odoo's own part is kept
        self.assertIn('offline-access-', response.text)
        self.assertNotIn('__OFFLINE_ACCESS_VERSION__', response.text)

    # ── Devices ──────────────────────────────────────────────────────────────

    def test_heartbeat_registers_device(self):
        self.authenticate('offline_worker', 'offline_worker')
        result = self.heartbeat()
        self.assertEqual(result, {'enabled': True, 'wipe': False, 'heartbeat_minutes': 15})
        device = self.Device.search([('device_uid', '=', DEVICE_UID)])
        self.assertEqual(len(device), 1)
        self.assertEqual(device.user_id, self.worker)
        self.assertEqual(device.name, 'Chrome on Android')
        self.assertTrue(device.installed)
        self.assertEqual(device.storage_used_mb, 5)
        self.assertTrue(device.sudo().session_identifier)

        self.heartbeat(installed=False)
        self.assertEqual(self.Device.search_count([('device_uid', '=', DEVICE_UID)]), 1)
        self.assertFalse(device.installed)

    def test_heartbeat_rejects_bad_requests(self):
        self.authenticate('offline_worker', 'offline_worker')
        result = self.rpc('/offline_access/heartbeat', device_uid='../../etc')
        self.assertFalse(result['enabled'])
        self.ICP.set_param('offline_access.enabled', False)
        self.assertFalse(self.heartbeat()['enabled'])
        self.assertFalse(self.Device.search_count([]))
        # Heartbeats need a signed in user.
        self.authenticate(None, None)
        response = self.url_open('/offline_access/heartbeat', data=json.dumps({'params': {'device_uid': DEVICE_UID}}),
                                 headers={'Content-Type': 'application/json'})
        self.assertIn('error', response.json())

    def test_revoke_signs_out_and_wipes(self):
        self.authenticate('offline_worker', 'offline_worker')
        self.heartbeat()
        device = self.Device.search([('device_uid', '=', DEVICE_UID)])
        device.action_revoke()
        self.assertEqual(device.state, 'revoked')
        self.assertEqual(device.revoked_by_id, self.env.user)
        # The session the device used is ended, so it is signed out.
        response = self.url_open('/offline_access/heartbeat', data=json.dumps({'params': {'device_uid': DEVICE_UID}}),
                                 headers={'Content-Type': 'application/json'})
        self.assertIn('error', response.json())
        # On the login page it learns it must wipe its data.
        self.assertEqual(self.rpc('/offline_access/device_status', device_uid=DEVICE_UID), {'wipe': True})
        self.assertTrue(device.wipe_sent_at)
        self.assertEqual(self.rpc('/offline_access/device_status', device_uid='a' * 32), {'wipe': False})

    def test_revoke_applies_to_whoever_is_signed_in(self):
        self.Device.create({'device_uid': DEVICE_UID, 'user_id': self.env.user.id}).action_revoke()
        self.authenticate('offline_worker', 'offline_worker')
        self.assertTrue(self.heartbeat()['wipe'])

    def test_cancel_revoke(self):
        device = self.Device.create({'device_uid': DEVICE_UID, 'user_id': self.worker.id})
        device.action_revoke()
        device.action_cancel_revoke()
        self.assertEqual(device.state, 'active')
        device.action_revoke()
        self.Device._check_wipe(DEVICE_UID)
        device.action_cancel_revoke()  # too late, the wipe was sent
        self.assertEqual(device.state, 'revoked')

    def test_cron_marks_stale(self):
        old = self.Device.create({
            'device_uid': DEVICE_UID, 'user_id': self.worker.id,
            'last_seen': fields.Datetime.now() - timedelta(days=20),
        })
        recent = self.Device.create({'device_uid': 'b' * 32, 'user_id': self.worker.id})
        self.Device._cron_mark_stale()
        self.assertEqual(old.state, 'stale')
        self.assertEqual(recent.state, 'active')

    # ── Settings and session ─────────────────────────────────────────────────

    def test_settings_icon_round_trip(self):
        png = make_png()
        self.env['res.config.settings'].create({'offline_access_icon': png}).execute()
        icon = self.Device._get_offline_access_config()['icon']
        self.assertTrue(icon.public)
        self.assertEqual(self.env['res.config.settings'].create({}).offline_access_icon, png)
        self.env['res.config.settings'].create({'offline_access_icon': False}).execute()
        self.assertFalse(icon.exists())
        self.assertFalse(self.Device._get_offline_access_config()['icon'])

    def test_session_info(self):
        self.authenticate('offline_worker', 'offline_worker')
        info = self.rpc('/web/session/get_session_info')
        self.assertTrue(info['offline_access']['enabled'])
        self.assertEqual(info['offline_access']['theme_color'], '#1f6f43')
        self.assertTrue(info['offline_access']['app_version'])

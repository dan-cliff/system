import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.offline_access.models import offline_access_model

DEVICE_UID = '7c19f59d-9cf8-4e97-bae2-f30906784e84'


@tagged('post_install', '-at_install')
class TestOfflineSync(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('offline_access.enabled', True)
        cls.OfflineModel = cls.env['offline.access.model']
        cls.OfflineModel.with_context(active_test=False).search([]).unlink()
        cls.worker = new_test_user(cls.env, login='offline_sync', password='offline_sync',
                                   groups='base.group_user')
        cls.acme = cls.env['res.partner'].create({'name': 'Acme Offline', 'is_company': True, 'city': 'Bendigo'})
        cls.contact = cls.env['res.partner'].create({'name': 'Jo Offline', 'parent_id': cls.acme.id})
        cls.other = cls.env['res.partner'].create({'name': 'Not A Company Offline'})
        # Saved a day ago, so they only count as changed on a full sync.
        cls.env.flush_all()
        cls.env.cr.execute("UPDATE res_partner SET write_date = write_date - interval '1 day' WHERE id IN %s",
                           [(cls.acme.id, cls.contact.id, cls.other.id)])
        cls.env.invalidate_all()
        cls.partners = cls.OfflineModel.create({
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'domain': "[('is_company', '=', True), ('name', 'ilike', 'Offline')]",
            'record_limit': 50,
        })

    def rpc(self, path, **params):
        response = self.url_open(path, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn('error', body, body.get('error'))
        return body['result']

    def sync(self, cursors=None):
        return self.rpc('/offline_access/sync', device_uid=DEVICE_UID, cursors=cursors or {})

    # ── Layout ───────────────────────────────────────────────────────────────

    def test_layout_follows_the_form(self):
        layout = self.partners.with_user(self.worker)._get_layout()
        fields_by_name = {f['name']: f for s in layout['sections'] for f in s['fields']}
        self.assertIn('name', fields_by_name)
        self.assertTrue(set(layout['list_columns']) <= set(fields_by_name))
        types = {f['type'] for f in fields_by_name.values()}
        self.assertTrue(types <= offline_access_model.SUPPORTED_TYPES)
        # Contacts are lines on the company form, with the inline list's columns.
        self.assertEqual(fields_by_name['child_ids']['type'], 'one2many')
        self.assertTrue(any(s['title'] for s in layout['sections']), 'Sections come from pages and groups')

    def test_layout_override(self):
        fields = self.env['ir.model.fields']._get('res.partner', 'city') | self.env['ir.model.fields']._get('res.partner', 'name')
        self.partners.write({'field_ids': [(6, 0, fields.ids)], 'list_field_ids': [(6, 0, fields[:1].ids)]})
        layout = self.partners.with_user(self.worker)._get_layout()
        self.assertEqual(sorted(f['name'] for s in layout['sections'] for f in s['fields']), ['city', 'name'])
        self.assertEqual(layout['list_columns'], ['city'])

    # ── Sync ─────────────────────────────────────────────────────────────────

    def test_sync_and_incremental_sync(self):
        self.authenticate('offline_sync', 'offline_sync')
        result = self.sync()
        self.assertTrue(result['enabled'])
        self.assertEqual(result['user_id'], self.worker.id)
        [payload] = result['models']
        self.assertEqual(payload['ids'], [self.acme.id])
        self.assertTrue(payload['full'])
        [record] = payload['records']
        self.assertEqual(record['display_name'], 'Acme Offline')
        self.assertEqual(record['child_ids']['count'], 1)
        self.assertEqual(record['child_ids']['lines'][0]['display_name'], 'Acme Offline, Jo Offline')

        # Nothing changed: no records sent again, the ids are still there.
        result = self.sync({str(payload['id']): payload['cursor']})
        [payload2] = result['models']
        self.assertFalse(payload2['full'])
        self.assertEqual(payload2['records'], [])
        self.assertEqual(payload2['ids'], [self.acme.id])

        # A new matching record is sent; changing the layout sends everything.
        bolt = self.env['res.partner'].create({'name': 'Bolt Offline', 'is_company': True})
        result = self.sync({str(payload['id']): payload2['cursor']})
        [payload3] = result['models']
        self.assertEqual([r['id'] for r in payload3['records']], [bolt.id])
        self.assertEqual(set(payload3['ids']), {self.acme.id, bolt.id})
        stale_cursor = dict(payload3['cursor'], layout='changed')
        [payload4] = self.sync({str(payload['id']): stale_cursor})['models']
        self.assertTrue(payload4['full'])
        self.assertEqual(len(payload4['records']), 2)

        log = self.env['offline.access.sync.log'].search([('user_id', '=', self.worker.id)])
        self.assertEqual(len(log), 4)
        self.assertEqual(set(log.mapped('state')), {'success'})

    def test_sync_respects_access(self):
        self.OfflineModel.create({'model_id': self.env['ir.model']._get_id('ir.rule')})
        self.authenticate('offline_sync', 'offline_sync')
        result = self.sync()
        self.assertEqual([m['model'] for m in result['models']], ['res.partner'])

    def test_domain_can_use_the_user(self):
        self.partners.domain = "[('id', '=', user.partner_id.id)]"
        self.authenticate('offline_sync', 'offline_sync')
        [payload] = self.sync()['models']
        self.assertEqual(payload['ids'], [self.worker.partner_id.id])

    def test_sync_updates_device_and_logs_errors(self):
        self.authenticate('offline_sync', 'offline_sync')
        self.rpc('/offline_access/heartbeat', device_uid=DEVICE_UID, browser='Chrome', platform='Android')
        self.sync()
        device = self.env['offline.access.device'].search([('device_uid', '=', DEVICE_UID)])
        self.assertTrue(device.last_sync)
        self.assertEqual(device.offline_record_count, 1)
        self.assertEqual(device.sync_log_count, 1)
        with patch.object(type(self.OfflineModel), '_sync_payload', side_effect=ValueError('broken filter')), \
                mute_logger('odoo.addons.offline_access.models.offline_access_device'):
            result = self.sync()
        self.assertEqual(result['error'], 'broken filter')
        error_log = self.env['offline.access.sync.log'].search([('state', '=', 'error')])
        self.assertEqual(error_log.device_id, device)

    def test_sync_wipes_revoked_device(self):
        self.authenticate('offline_sync', 'offline_sync')
        self.rpc('/offline_access/heartbeat', device_uid=DEVICE_UID)
        device = self.env['offline.access.device'].search([('device_uid', '=', DEVICE_UID)])
        device.state = 'revoked'
        self.assertTrue(self.sync()['wipe'])

    def test_sync_needs_offline_access_on(self):
        self.env['ir.config_parameter'].sudo().set_param('offline_access.enabled', False)
        self.authenticate('offline_sync', 'offline_sync')
        self.assertEqual(self.sync(), {'enabled': False})

    # ── Configuration ────────────────────────────────────────────────────────

    def test_invalid_filter_rejected(self):
        with self.assertRaises(Exception):
            self.partners.domain = "[('no_such_field', '=', 1)]"

    def test_add_suggested_models(self):
        suggestions = [('res.partner', 100, []), ('res.country', 300, []), ('no.such.model', 10, [])]
        self.partners.unlink()
        with patch.object(offline_access_model, 'SUGGESTED_MODELS', suggestions):
            self.OfflineModel.action_add_suggested()
            self.OfflineModel.action_add_suggested()  # adds nothing twice
        self.assertEqual(sorted(self.OfflineModel.search([]).mapped('model_name')), ['res.country', 'res.partner'])
        self.assertEqual(self.OfflineModel.search([('model_name', '=', 'res.partner')]).record_limit, 100)

    def test_purge_sync_log(self):
        Log = self.env['offline.access.sync.log']
        old = Log.create({'user_id': self.worker.id, 'date': fields.Datetime.now() - timedelta(days=40)})
        recent = Log.create({'user_id': self.worker.id})
        Log._cron_purge()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    # ── Offline page and service worker ──────────────────────────────────────

    def test_offline_page(self):
        page = self.url_open('/odoo/offline')
        self.assertEqual(page.status_code, 200)
        self.assertIn('/offline_access/static/src/offline_app/offline_app.js?v=', page.text)
        self.assertNotIn('offline_sync', page.text)  # cached for everyone: no user data
        self.env['ir.config_parameter'].sudo().set_param('offline_access.enabled', False)
        self.assertNotIn('offline_app.js', self.url_open('/odoo/offline').text)

    def test_service_worker_precaches_offline_screens(self):
        script = self.url_open('/web/service-worker.js').text
        self.assertIn('/offline_access/static/src/offline_app/offline_app.js?v=', script)
        self.assertIn('/offline_access/static/src/offline_store.js?v=', script)
        self.assertNotIn('__OFFLINE_ACCESS_PRECACHE__', script)

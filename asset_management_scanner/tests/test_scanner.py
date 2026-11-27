# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged


class AssetScannerCommon:

    @classmethod
    def _assets(cls, env):
        tracked = env['asset.type'].create({
            'name': 'Scanner Machinery', 'has_maintenance': True, 'has_usage_tracking': True})
        plain = env['asset.type'].create({'name': 'Scanner Furniture'})
        Asset = env['asset.asset']
        mower = Asset.create({'name': 'Scanner Mower', 'asset_type_id': tracked.id, 'serial_number': 'TSCAN-A1'})
        trimmer = Asset.create({'name': 'Scanner Trimmer', 'asset_type_id': tracked.id,
                                'registration_number': 'TSCAN-A2'})
        desk = Asset.create({'name': 'Scanner Desk', 'asset_type_id': plain.id, 'serial_number': 'TSCAN-A3'})
        return mower, trimmer, desk


@tagged('post_install', '-at_install')
class TestAssetScanner(AssetScannerCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mower, cls.trimmer, cls.desk = cls._assets(cls.env)
        cls.Asset = cls.env['asset.asset']

    def test_find_asset(self):
        self.mower.action_generate_token()
        self.assertEqual(self.Asset.scanner_find_asset('TSCAN-A1'), self.mower.id)
        self.assertEqual(self.Asset.scanner_find_asset(' tscan-a2 '), self.trimmer.id)
        self.assertEqual(self.Asset.scanner_find_asset(self.mower.asset_number), self.mower.id)
        self.assertEqual(self.Asset.scanner_find_asset(self.mower.cp_url), self.mower.id)
        self.assertFalse(self.Asset.scanner_find_asset('NOPE'))
        self.assertEqual(self.mower.action_return_to_scanner()['url'], '/odoo/scanner')

    def test_setup(self):
        setup = self.Asset.scanner_bulk_setup('maintenance')
        by_name = {f['name']: f for f in setup['fields']}
        self.assertNotIn('asset_id', by_name)
        self.assertEqual(by_name['maintenance_type_id']['type'], 'select')
        self.assertEqual(by_name['supplier_id']['type'], 'record')
        self.assertEqual(by_name['date']['default'], fields.Date.to_string(fields.Date.context_today(self.Asset)))
        self.assertEqual(by_name['performed_by']['default'], self.env.user.id)
        self.assertTrue(by_name['description']['required'])
        defect = {f['name']: f for f in self.Asset.scanner_bulk_setup('defect')['fields']}
        self.assertEqual(defect['state']['default'], 'open')
        self.assertEqual(defect['resolved_date']['show_if'], ['state', 'resolved'])

    def test_scan_checks_features(self):
        self.assertEqual(self.Asset.scanner_bulk_find_asset('usage', 'TSCAN-A1')['id'], self.mower.id)
        self.assertIn('error', self.Asset.scanner_bulk_find_asset('usage', 'TSCAN-A3'))
        self.assertIn('error', self.Asset.scanner_bulk_find_asset('maintenance', 'TSCAN-A3'))
        self.assertEqual(self.Asset.scanner_bulk_find_asset('defect', 'TSCAN-A3')['id'], self.desk.id)
        self.assertIn('error', self.Asset.scanner_bulk_find_asset('defect', 'NOPE'))

    def test_generate_maintenance(self):
        kind = self.env['asset.maintenance.type'].create({'name': 'Scanner Service'})
        result = self.Asset.scanner_bulk_generate('maintenance', [self.mower.id, self.trimmer.id], {
            'date': '2026-11-01', 'maintenance_type_id': kind.id, 'description': 'Blade sharpened',
            'cost': 12.5, 'performed_by': self.env.user.id,
        })
        self.assertEqual(result, {'count': 2, 'label': 'Maintenance Log'})
        logs = (self.mower | self.trimmer).maintenance_log_ids
        self.assertEqual(len(logs), 2)
        self.assertEqual(set(logs.mapped('description')), {'Blade sharpened'})
        self.assertEqual(logs.maintenance_type_id, kind)
        self.assertEqual(logs.mapped('cost'), [12.5, 12.5])
        self.assertEqual(set(logs.mapped('date')), {fields.Date.to_date('2026-11-01')})
        with self.assertRaises(UserError):
            self.Asset.scanner_bulk_generate('maintenance', [self.desk.id], {'description': 'No'})
        with self.assertRaises(UserError):
            self.Asset.scanner_bulk_generate('maintenance', [self.mower.id], {'description': ''})
        with self.assertRaises(UserError):
            self.Asset.scanner_bulk_generate('maintenance', [], {'description': 'Nothing scanned'})

    def test_generate_usage_and_defect(self):
        result = self.Asset.scanner_bulk_generate('usage', [self.mower.id, self.trimmer.id], {
            'date': '2026-11-02', 'user_id': self.env.user.id, 'reading': 8, 'notes': 'Day shift'})
        self.assertEqual(result['count'], 2)
        self.assertEqual(self.mower.latest_usage_reading, 8)
        result = self.Asset.scanner_bulk_generate('defect', [self.desk.id], {
            'date': '2026-11-03', 'description': 'Wobbly leg', 'state': 'open',
            'resolved_date': '2026-11-04', 'resolution_notes': 'Ignored while open'})
        self.assertEqual(result, {'count': 1, 'label': 'Defect Report'})
        defect = self.desk.defect_ids
        self.assertEqual(defect.state, 'open')
        self.assertFalse(defect.resolved_date)
        self.assertFalse(defect.resolution_notes)


@tagged('post_install', '-at_install')
class TestAssetScannerTour(AssetScannerCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.env.ref('base.user_admin').group_ids = [(4, self.env.ref('asset_management.group_asset_user').id)]
        self.mower, self.trimmer, self.desk = self._assets(self.env)

    def test_bulk_defects(self):
        self.start_tour('/odoo/scanner', 'asset_management_scanner_bulk_defect', login='admin')
        self.assertEqual(self.mower.defect_ids.description, 'Cracked guard')
        self.assertEqual(self.trimmer.defect_ids.description, 'Cracked guard')
        self.assertFalse(self.desk.defect_ids)

    def test_lookup(self):
        self.start_tour('/odoo/scanner', 'asset_management_scanner_lookup', login='admin')

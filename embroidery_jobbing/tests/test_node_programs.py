# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase


class TestNodePrograms(TransactionCase):

    def test_shipped_programs(self):
        Program = self.env['iot.program']
        bridge = Program.search([('role', '=', 'embroidery_bridge')])
        display = Program.search([('role', '=', 'embroidery_display')])
        self.assertEqual(bridge.current_version_id.entrypoint, 'embroidery_bridge.py')
        self.assertEqual(bridge.current_version_id.source, 'builtin')
        self.assertIn('config.json', bridge.current_version_id.file_ids.mapped('path'))
        self.assertFalse(display.current_version_id.entrypoint)
        self.assertEqual(display.current_version_id.home_path, '/embroidery/node/v1/display/page')
        self.assertEqual(display.current_version_id.setup_script, 'setup.sh')
        # Running the sync again with unchanged files adds no version.
        versions = bridge.version_ids
        Program._iot_sync_builtin()
        self.assertEqual(bridge.version_ids, versions)

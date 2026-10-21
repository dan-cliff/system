# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError

from .common import EmbroideryCase


class TestEmbroideryJob(EmbroideryCase):

    def test_design_read_on_upload(self):
        self.assertEqual(self.design.stitch_count, 150)
        self.assertEqual(self.design.color_ids.mapped('name'), ['Black', 'Red'])
        self.assertTrue(self.design.image_128)
        with self.assertRaises(ValidationError):
            self.env['embroidery.design'].create({
                'name': 'Bad', 'design_file': 'bm90IHBlcw==', 'design_filename': 'bad.pes',
            })

    def test_machine_from_model(self):
        self.assertEqual(self.machine.needle_count, 10)
        self.assertEqual(self.machine.speed_spm, 800)
        self.assertIn(self.env.ref('embroidery_jobbing.hoop_extra_large'), self.machine.hoop_ids)

    def test_send_and_stitch(self):
        self.assertTrue(self.job.name.startswith('EMB/'))
        self.job.action_send_to_machine()
        stitchout = self.job.stitchout_ids
        self.assertEqual(stitchout.state, 'queued')
        self.assertEqual(self.job.state, 'in_progress')
        self.assertEqual(self.machine.status, 'offline')  # the bridge hasn't polled
        # The machine can only take one design at a time.
        with self.assertRaises(UserError):
            self.job.action_send_to_machine()

        stitchout._apply_report({'status': 'sent'})
        stitchout._apply_report({'status': 'stitching', 'stitch': 0})
        stitchout._apply_report({'stitch': 120, 'speed': 750})
        self.assertTrue(stitchout.has_live_data)
        self.assertEqual(stitchout.current_color, 2)
        self.assertAlmostEqual(stitchout.progress, 80.0)
        self.assertIn('color_change', stitchout.event_ids.mapped('event_type'))

        stitchout._apply_report({'status': 'error', 'message': 'Upper thread break', 'error_code': 'E1'})
        self.assertEqual(stitchout.state, 'error')
        self.assertEqual(stitchout.error_count, 1)
        self.assertEqual(self.job.error_count, 1)
        stitchout._apply_report({'status': 'stitching'})
        stitchout._apply_report({'status': 'done'})
        self.assertEqual(stitchout.progress, 100.0)
        self.assertEqual(self.job.qty_done, 1)
        self.assertEqual(self.job.state, 'in_progress')

        self.job.action_send_to_machine()
        second = self.job.stitchout_ids - stitchout
        self.assertEqual(second.piece_number, 2)
        second._apply_report({'status': 'done'})
        self.assertEqual(self.job.qty_done, 2)
        self.assertEqual(self.job.state, 'done')

    def test_eta_from_measured_speed(self):
        self.job.action_send_to_machine()
        stitchout = self.job.stitchout_ids
        start = fields.Datetime.now()
        stitchout._apply_report({'status': 'stitching'})
        stitchout.stitching_since = start - timedelta(seconds=60)
        stitchout._apply_report({'stitch': 50})
        # 50 stitches in 60 s: the other 100 take 120 s.
        with patch.object(fields.Datetime, 'now', return_value=start):
            stitchout.invalidate_recordset(['progress', 'remaining_seconds'])
            self.assertEqual(stitchout.remaining_seconds, 120)

    def test_manual_machine(self):
        self.machine.driver = 'manual'
        self.job.action_send_to_machine()
        stitchout = self.job.stitchout_ids
        self.assertEqual(stitchout.state, 'sent')
        stitchout.action_operator_start()
        self.assertEqual(stitchout.state, 'stitching')
        data = self.job.embroidery_progress_data()
        self.assertFalse(data['live'])
        self.assertEqual(data['total_stitches'], 150)
        self.env['embroidery.stitchout.error.wizard'].create({
            'stitchout_id': stitchout.id, 'message': 'Needle broke',
        }).action_report()
        self.assertEqual(stitchout.state, 'error')
        self.job.action_cancel()
        self.assertEqual(stitchout.state, 'cancelled')
        self.assertEqual(self.job.state, 'cancelled')

    def test_warnings(self):
        self.job.hoop_id = self.env.ref('embroidery_jobbing.hoop_small')
        self.assertFalse(self.job.warning_message)
        self.design.write({'width_mm': 50, 'height_mm': 70})
        self.job.invalidate_recordset(['warning_message'])
        self.assertIn('bigger than', self.job.warning_message)

# -*- coding: utf-8 -*-
from odoo.tests import BaseCase

from ..lib import pes
from .common import SAMPLE_BLOCKS, make_pes


class TestPes(BaseCase):

    def test_read_pes(self):
        design = pes.read_pes(make_pes(SAMPLE_BLOCKS, label='LOGO'))
        self.assertEqual(design.label, 'LOGO')
        self.assertEqual(design.version, '0001')
        self.assertEqual(design.stitch_count, 150)
        self.assertEqual(design.jump_count, 2)
        self.assertEqual([c['name'] for c in design.colors], ['Black', 'Red'])
        self.assertEqual([c['stitches'] for c in design.colors], [100, 50])
        self.assertEqual(design.color_change_count, 1)
        self.assertAlmostEqual(design.width_mm, 10.0)
        self.assertAlmostEqual(design.height_mm, 5.0)
        self.assertTrue(design.preview_png().startswith(b'\x89PNG'))

    def test_long_moves(self):
        # Moves beyond 7 bits are stored as 12 bit values.
        design = pes.read_pes(make_pes([(1, [(300, -200), (-300, 200)])]))
        self.assertEqual(design.stitch_count, 2)
        self.assertAlmostEqual(design.width_mm, 30.0)
        self.assertAlmostEqual(design.height_mm, 20.0)

    def test_not_pes(self):
        with self.assertRaises(pes.PesError):
            pes.read_pes(b'not an embroidery file')

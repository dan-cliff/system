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

    def test_write_pes_round_trip(self):
        # Two colours, the first used again at the end: the chart lists each
        # thread once and the reader gives every block its thread back.
        square = [(0, 0, pes.STITCH)] + [(x * 25, 0, pes.STITCH) for x in range(1, 9)]
        line = [(0, 100, pes.STITCH)] + [(x * 25, 100, pes.STITCH) for x in range(1, 5)]
        again = [(0, 200, pes.STITCH), (30, 200, pes.STITCH)]
        threads = [
            {'name': 'Scarlet', 'hex': '#d0102a', 'catalog': '1747', 'brand': 'Madeira'},
            {'name': 'Navy', 'hex': '#1a2a60'},
            {'name': 'Scarlet', 'hex': '#d0102a', 'catalog': '1747', 'brand': 'Madeira'},
        ]
        data = pes.write_pes([square, line, again], threads, label='ROUND')
        design = pes.read_pes(data)
        self.assertEqual(design.version, '0060')
        self.assertEqual(design.label, 'ROUND')
        self.assertEqual([c['name'] for c in design.colors], ['Scarlet', 'Navy', 'Scarlet'])
        self.assertEqual([c['hex'] for c in design.colors], ['#d0102a', '#1a2a60', '#d0102a'])
        self.assertEqual(design.colors[0]['catalog'], '1747')
        self.assertEqual(design.colors[0]['brand'], 'Madeira')
        self.assertAlmostEqual(design.width_mm, 20.0)
        self.assertAlmostEqual(design.height_mm, 20.0)
        # Distinct threads get distinct palette indexes (how Brother maps the chart).
        self.assertNotEqual(design.colors[0]['index'], design.colors[1]['index'])
        self.assertEqual(design.colors[0]['index'], design.colors[2]['index'])
        # The commands split back into the same three blocks.
        blocks = [[]]
        for command in design.commands:
            if command[2] == pes.COLOR:
                blocks.append([])
            else:
                blocks[-1].append(command)
        self.assertEqual(len(blocks), 3)
        stitched = [[c for c in block if c[2] == pes.STITCH] for block in blocks]
        self.assertGreaterEqual(len(stitched[0]), 9)

    def test_write_pes_long_moves(self):
        # Moves longer than a stitch become trims; very long ones are split.
        data = pes.write_pes([[(0, 0, pes.STITCH), (10, 0, pes.STITCH),
                               (3000, 0, pes.TRIM), (3000, 0, pes.STITCH), (3010, 0, pes.STITCH)]],
                             [{'name': 'Black', 'hex': '#000000'}])
        design = pes.read_pes(data)
        self.assertAlmostEqual(design.width_mm, 301.0)
        self.assertGreaterEqual(design.trim_count, 1)

    def test_write_needs_a_thread_per_block(self):
        with self.assertRaises(pes.PesError):
            pes.write_pes([[(0, 0, pes.STITCH)]], [])

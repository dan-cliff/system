# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..lib import pes
from .common import SAMPLE_BLOCKS, make_pes
from .test_digitise import logo_png


@tagged('post_install', '-at_install')
class TestThreads(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['product.category'].create({'name': 'Threads', 'is_thread': True})
        cls.maker = cls.env['res.partner'].create({'name': 'Madeira', 'is_company': True})
        cls.polyester = cls.env.ref('embroidery_jobbing.thread_type_polyester')

        def thread(name, colour, code):
            return cls.env['product.product'].create({
                'name': name, 'categ_id': cls.category.id, 'default_code': code,
                'thread_manufacturer_id': cls.maker.id, 'thread_name': name,
                'thread_color': colour, 'thread_type_id': cls.polyester.id,
            })

        cls.scarlet = thread('Scarlet', '#D0102A', '1747')
        cls.cherry = thread('Cherry', '#a00020', '1781')
        cls.navy = thread('Navy', '1a2a60', '1843')
        cls.white = thread('White', '#fff', '1001')

    def test_advanced_details(self):
        other = self.env['product.template'].create({'name': 'Polo shirt'})
        self.assertFalse(other.show_advanced_details)
        self.assertTrue(self.scarlet.product_tmpl_id.show_advanced_details)
        other.categ_id = self.category
        self.assertTrue(other.show_advanced_details)

    def test_thread_colour(self):
        # Hex codes are stored as #rrggbb whatever way they are typed.
        self.assertEqual(self.scarlet.thread_color, '#d0102a')
        self.assertEqual(self.navy.thread_color, '#1a2a60')
        self.assertEqual(self.white.thread_color, '#ffffff')
        with self.assertRaises(ValidationError):
            self.scarlet.thread_color = 'red'

    def test_catalogue(self):
        Product = self.env['product.product']
        self.assertEqual(set(Product._embroidery_thread_catalogue().ids) >= set(
            (self.scarlet | self.cherry | self.navy | self.white).ids), True)
        other_maker = self.env['res.partner'].create({'name': 'Isacord', 'is_company': True})
        self.assertFalse(Product._embroidery_thread_catalogue(manufacturer=other_maker))
        self.assertEqual(Product._embroidery_thread_catalogue(manufacturer=self.maker),
                         self.scarlet | self.cherry | self.navy | self.white)

    def test_design_from_artwork(self):
        design = self.env['embroidery.design'].create({
            'artwork_file': base64.b64encode(logo_png()),
            'artwork_filename': 'Club Logo.png',
            'digitise_width_mm': 100,
            'digitise_manufacturer_id': self.maker.id,
        })
        self.assertEqual(design.name, 'Club Logo')
        self.assertEqual(design.design_filename, 'Club Logo.pes')
        self.assertTrue(design.design_file)
        self.assertTrue(design.image_1920)
        self.assertEqual(set(design.color_ids.product_id.ids), {self.scarlet.id, self.navy.id, self.white.id})
        self.assertTrue(all(line.color_difference < 10 for line in design.color_ids))
        self.assertEqual(design.color_ids.filtered(lambda l: l.product_id == self.scarlet).color_hex, '#d0102a')
        self.assertGreater(design.stitch_count, 1000)
        # The file carries the threads.
        read = pes.read_pes(base64.b64decode(design.with_context(bin_size=False).design_file))
        self.assertIn('1747', [c.get('catalog') for c in read.colors])
        self.assertIn('Madeira', [c.get('brand') for c in read.colors])

        # Picking another thread rewrites the file with its colour.
        line = design.color_ids.filtered(lambda l: l.product_id == self.scarlet)
        stitches = design.stitch_count
        design.write({'color_ids': [(1, line.id, {'product_id': self.cherry.id})]})
        line = design.color_ids.filtered(lambda l: l.product_id == self.cherry)
        self.assertEqual(line.color_hex, '#a00020')
        self.assertEqual(design.stitch_count, stitches)
        read = pes.read_pes(base64.b64decode(design.with_context(bin_size=False).design_file))
        self.assertIn('#a00020', [c['hex'] for c in read.colors])

        # Changing a setting digitises again; Cherry goes back to Scarlet.
        design.digitise_max_colors = 2
        self.assertEqual(set(design.color_ids.product_id.ids), {self.scarlet.id, self.navy.id})

        # A .pes uploaded over it replaces it and forgets the artwork.
        design.write({'design_file': base64.b64encode(make_pes(SAMPLE_BLOCKS)), 'design_filename': 'new.pes'})
        self.assertFalse(design.artwork_file)
        self.assertEqual(design.color_count, 2)
        self.assertFalse(design.color_ids.product_id)

    def test_design_needs_a_file(self):
        with self.assertRaises(ValidationError):
            self.env['embroidery.design'].create({'name': 'Nothing'})
        with self.assertRaises(ValidationError):
            self.env['embroidery.design'].create({
                'name': 'Wrong', 'artwork_file': base64.b64encode(b'x'), 'artwork_filename': 'x.gif'})

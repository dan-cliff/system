# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from ..tools import svg_tools
from .common import SVG_BASE


@tagged('post_install', '-at_install')
class TestSvgTools(BaseCase):

    def test_sanitize_removes_active_content(self):
        data = svg_tools.sanitized_svg(SVG_BASE)
        self.assertNotIn(b'<script', data)
        self.assertNotIn(b'onload', data)
        self.assertNotIn(b'example.com', data)
        self.assertIn(b'outline', data)

    def test_entities_are_not_resolved(self):
        xxe = (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
               b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&x;</text></svg>')
        data = svg_tools.sanitized_svg(xxe)
        self.assertNotIn(b'root:', data)

    def test_not_svg(self):
        with self.assertRaises(svg_tools.SvgError):
            svg_tools.parse_svg(b'<html xmlns="http://www.w3.org/1999/xhtml"/>')
        with self.assertRaises(svg_tools.SvgError):
            svg_tools.parse_svg(b'not xml')

    def test_view_box_and_size(self):
        root = svg_tools.parse_svg(SVG_BASE)
        self.assertEqual(svg_tools.view_box(root), (0.0, 0.0, 80.0, 40.0))
        width, height = svg_tools.size_mm(root)
        self.assertAlmostEqual(width, 80.0, places=3)
        self.assertAlmostEqual(height, 40.0, places=3)

    def test_build_svg_in_mm_with_prefixed_ids(self):
        spec = {
            'operation': 'cut', 'width': 100, 'height': 50,
            'base': {'data': SVG_BASE, 'ext': 'svg'},
            'elements': [
                {'type': 'text', 'x': 5, 'y': 5, 'w': 90, 'h': 20, 'text': 'Hello', 'align': 'center'},
                {'type': 'image', 'x': 0, 'y': 25, 'w': 50, 'h': 25, 'image': SVG_BASE, 'fit': 'cover'},
            ],
        }
        root = etree.fromstring(svg_tools.build_svg(spec))
        self.assertEqual(root.get('width'), '100mm')
        self.assertEqual(root.get('viewBox'), '0 0 100 50')
        ids = [el.get('id') for el in root.iter() if el.get('id')]
        self.assertEqual(len(ids), len(set(ids)), 'embedded SVG ids must not clash')
        self.assertIn('Hello', etree.tostring(root, encoding='unicode'))

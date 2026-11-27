# -*- coding: utf-8 -*-
import io

from PIL import Image, ImageDraw

from odoo.tests import BaseCase

from ..lib import digitise, pes, svg

THREADS = [
    {'name': 'Scarlet', 'hex': '#d0102a'},
    {'name': 'Navy', 'hex': '#1a2a60'},
    {'name': 'Sunflower', 'hex': '#ffcc00'},
    {'name': 'White', 'hex': '#ffffff'},
    {'name': 'Black', 'hex': '#000000'},
]


def logo_png(transparent=False):
    """A red ring (white inside) beside a navy square, on white or transparent."""
    image = Image.new('RGBA', (800, 400), (255, 255, 255, 0 if transparent else 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 360, 360), fill='#e30613')
    draw.ellipse((140, 140, 260, 260), fill='#ffffff')
    draw.rectangle((440, 80, 760, 320), fill='#1d2b6b')
    image = image.resize((400, 200), Image.Resampling.LANCZOS)  # soft, anti-aliased edges
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


class TestDigitise(BaseCase):

    def test_delta_e(self):
        # A published CIEDE2000 test pair (Sharma, Wu and Dalal, pair 1).
        self.assertAlmostEqual(digitise.delta_e((50, 2.6772, -79.7751), (50, 0, -82.7485)), 2.0425, places=3)
        self.assertEqual(digitise.delta_e((50, 10, 10), (50, 10, 10)), 0)

    def test_nearest_thread(self):
        thread, difference = digitise.nearest_thread((227, 6, 19), [dict(t) for t in THREADS])
        self.assertEqual(thread['name'], 'Scarlet')
        self.assertLess(difference, 10)

    def test_digitise_png(self):
        result = digitise.digitise(logo_png(), 'logo.png', THREADS, digitise.Settings(width_mm=100))
        # The white page around the logo is dropped, the white inside the ring stays.
        self.assertEqual(sorted(t['name'] for t in result.threads), ['Navy', 'Scarlet', 'White'])
        self.assertEqual(len(result.blocks), len(result.colors))
        design = pes.read_pes(result.pes('LOGO'))
        self.assertEqual([c['name'] for c in design.colors], [t['name'] for t in result.threads])
        self.assertGreater(design.stitch_count, 1000)
        # 100 mm wide artwork; the logo itself spans 90 mm of it.
        self.assertAlmostEqual(design.width_mm, 90, delta=2)
        self.assertAlmostEqual(design.height_mm, 40, delta=2)

    def test_transparent_background(self):
        result = digitise.digitise(logo_png(transparent=True), 'logo.png', THREADS,
                                   digitise.Settings(width_mm=100))
        self.assertEqual(sorted(t['name'] for t in result.threads), ['Navy', 'Scarlet', 'White'])

    def test_opaque_artwork_touching_the_edge(self):
        # Without transparency the colour around the edge is the background;
        # artwork on a transparent page keeps every colour, even at the edge.
        image = Image.new('RGBA', (200, 100), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((0, 0, 99, 99), fill='#1d2b6b')
        ImageDraw.Draw(image).ellipse((120, 20, 180, 80), fill='#e30613')
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        result = digitise.digitise(buffer.getvalue(), 'edge.png', THREADS, digitise.Settings(width_mm=100))
        self.assertEqual(sorted(t['name'] for t in result.threads), ['Navy', 'Scarlet'])

    def test_max_colors(self):
        result = digitise.digitise(logo_png(), 'logo.png', THREADS, digitise.Settings(width_mm=100, max_colors=2))
        self.assertEqual(sorted(t['name'] for t in result.threads), ['Navy', 'Scarlet'])

    def test_brother_palette_without_threads(self):
        result = digitise.digitise(logo_png(), 'logo.png', [], digitise.Settings(width_mm=60))
        self.assertTrue(all(t['brand'] == 'Brother' for t in result.threads))

    def test_digitise_svg(self):
        data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
            <style>.navy { fill: #1a2a60 }</style>
            <path class="navy" d="M0 0h100v100H0z M25 25v50h50V25z"/>
            <circle cx="150" cy="50" r="40" fill="#d0102a"/>
        </svg>'''
        result = digitise.digitise(data, 'logo.svg', THREADS, digitise.Settings(width_mm=100))
        self.assertEqual([t['name'] for t in result.threads], ['Navy', 'Scarlet'])
        design = pes.read_pes(result.pes())
        self.assertAlmostEqual(design.width_mm, 95, delta=2)

    def test_svg_render(self):
        data = b'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
                        width="100" height="100">
            <defs><linearGradient id="g"><stop offset="0" stop-color="#00ff00"/></linearGradient>
                  <rect id="r" width="10" height="10"/></defs>
            <path d="M10 10 L50 10 L50 50 Z" fill="red" fill-rule="evenodd"/>
            <g transform="translate(60 60)"><use xlink:href="#r" fill="url(#g)"/></g>
            <path d="M60 10 a 15 15 0 1 1 0.1 0" fill="none" stroke="#0000ff" stroke-width="4"/>
        </svg>'''
        image = svg.render(data, 100, 100)
        self.assertEqual(image.getpixel((45, 15))[:3], (255, 0, 0))
        self.assertEqual(image.getpixel((15, 45))[3], 0)  # outside the triangle
        self.assertEqual(image.getpixel((65, 65))[:3], (0, 255, 0))
        self.assertEqual(image.getpixel((60, 10))[:3], (0, 0, 255))

    def test_svg_holes_nonzero(self):
        # Outline clockwise, hole anticlockwise: the hole stays empty.
        data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <path d="M0 0H100V100H0Z M30 30V70H70V30Z" fill="#000"/></svg>'''
        image = svg.render(data, 100, 100)
        self.assertEqual(image.getpixel((10, 10))[3], 255)
        self.assertEqual(image.getpixel((50, 50))[3], 0)

    def test_bad_artwork(self):
        with self.assertRaises(digitise.DigitiseError):
            digitise.digitise(b'not a picture', 'x.png', THREADS)
        with self.assertRaises(digitise.DigitiseError):
            digitise.digitise(b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'x.svg', THREADS)
        with self.assertRaises(digitise.DigitiseError):
            digitise.Settings(width_mm=0, height_mm=0)

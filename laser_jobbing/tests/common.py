# -*- coding: utf-8 -*-
import base64
import io

from PIL import Image

from odoo.tests.common import TransactionCase

SVG_BASE = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="40mm" viewBox="0 0 80 40" onload="alert(1)">
  <script>alert(1)</script>
  <defs><linearGradient id="g"><stop offset="0" stop-color="#000"/></linearGradient></defs>
  <rect id="outline" x="1" y="1" width="78" height="38" rx="4" fill="none" stroke="url(#g)"/>
  <use href="#outline"/>
  <image href="https://example.com/tracker.png" width="1" height="1"/>
</svg>"""


def picture(ext, size=(120, 80), color=(200, 30, 30)):
    """Picture bytes in a file format (by extension)."""
    pil = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'tif': 'TIFF', 'tiff': 'TIFF'}.get(ext, ext.upper())
    image = Image.new('RGB', size, color)
    out = io.BytesIO()
    image.save(out, pil)
    return out.getvalue()


def b64(data):
    return base64.b64encode(data)


class LaserCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.engrave_template = cls.env['laser.template'].create({
            'name': 'Engraved Board',
            'operation': 'engrave',
            'width_mm': 60,
            'height_mm': 40,
            'dpi': 100,
            'base_file': b64(picture('png')),
            'base_filename': 'board.png',
            'element_ids': [
                (0, 0, {'name': 'Name', 'element_type': 'text', 'x_mm': 5, 'y_mm': 5,
                        'width_mm': 50, 'height_mm': 10, 'default_text': 'Your Name', 'max_length': 20}),
                (0, 0, {'name': 'Photo', 'element_type': 'image', 'x_mm': 5, 'y_mm': 18,
                        'width_mm': 50, 'height_mm': 20, 'required': False}),
            ],
        })
        cls.cut_template = cls.env['laser.template'].create({
            'name': 'Cut Keyring',
            'operation': 'cut',
            'width_mm': 80,
            'height_mm': 40,
            'base_file': b64(SVG_BASE),
            'base_filename': 'keyring.svg',
            'element_ids': [
                (0, 0, {'name': 'Initials', 'element_type': 'text', 'x_mm': 10, 'y_mm': 10,
                        'width_mm': 60, 'height_mm': 20, 'default_text': 'AB'}),
                (0, 0, {'name': 'Logo', 'element_type': 'image', 'x_mm': 60, 'y_mm': 5,
                        'width_mm': 15, 'height_mm': 15, 'required': False}),
            ],
        })

    def make_job(self, template, **values):
        return self.env['laser.job'].create(dict({'template_id': template.id}, **values))

    def value(self, job, name):
        return job.value_ids.filtered(lambda v: v.element_id.name == name)

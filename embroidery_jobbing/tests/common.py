# -*- coding: utf-8 -*-
import base64
import struct

from odoo.tests import TransactionCase


def _encode(value, flags=0):
    if not flags and -64 <= value <= 63:
        return bytes([value & 0x7F])
    value &= 0xFFF
    return bytes([0x80 | flags | (value >> 8), value & 0xFF])


def make_pes(blocks, label='TEST'):
    """A minimal .pes file. ``blocks`` is a list of (palette index, moves);
    a move is (dx, dy) for a stitch or (dx, dy, 'jump') in 0.1 mm."""
    stitches = bytearray()
    for number, (_color, moves) in enumerate(blocks):
        if number:
            stitches += b'\xfe\xb0' + bytes([2 if number % 2 else 1])
        for move in moves:
            flags = 0x10 if len(move) > 2 else 0
            stitches += _encode(move[0], flags) + _encode(move[1], flags)
    stitches += b'\xff\x00'
    colors = bytes(color for color, _moves in blocks)
    header = b'LA:' + label.ljust(16).encode()[:16] + b'\r' + b' ' * 12 + b'\xff\x00' + bytes([6, 38])
    header += b' ' * 12 + bytes([len(colors) - 1]) + colors
    header = header.ljust(512, b' ')
    pec = header + b'\x00\x00' + struct.pack('<I', len(stitches) + 20)[:3] + b'\x31\xff\xf0'
    pec += struct.pack('<4H', 0, 0, 0x1E0, 0x1B0) + stitches
    return b'#PES0001' + struct.pack('<I', 12) + pec


# Two colours: 100 stitches of Black then 50 of Red, 10 x 5 mm.
SAMPLE_BLOCKS = [
    (20, [(0, 0, 'jump')] + [(1, 0)] * 100),
    (5, [(-100, 50, 'jump')] + [(2, -1)] * 50),
]


class EmbroideryCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.design = cls.env['embroidery.design'].create({
            'name': 'Logo',
            'design_file': base64.b64encode(make_pes(SAMPLE_BLOCKS)),
            'design_filename': 'logo.pes',
        })
        cls.bridge = cls.env['embroidery.bridge'].create({'name': 'Workshop Pi'})
        cls.machine = cls.env['embroidery.machine'].create({
            'name': 'PR1060W #1',
            'machine_model_id': cls.env.ref('embroidery_jobbing.machine_model_brother_pr1060w').id,
            'driver': 'simulator',
            'bridge_id': cls.bridge.id,
        })
        cls.job = cls.env['embroidery.job'].create({
            'title': 'Club polos',
            'product_qty': 2,
            'design_id': cls.design.id,
            'machine_id': cls.machine.id,
        })

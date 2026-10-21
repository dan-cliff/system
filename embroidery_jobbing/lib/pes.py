# -*- coding: utf-8 -*-
"""Read Brother .pes embroidery files.

A .pes file starts with "#PES" and a version, then the offset of its PEC
section. The PEC section is what Brother machines stitch from: a 512 byte
header (label, colour count and colour palette indexes) followed by the
stitch block. Coordinates are in 0.1 mm.

Only the standard library and Pillow (for the preview) are used, so this
module can also be imported by the Embroidery Bridge.
"""
import io
import struct

# Brother's PEC thread palette: index -> (name, (r, g, b)). Index 0 is unknown.
PEC_THREADS = [
    ('Unknown', (0, 0, 0)),
    ('Prussian Blue', (26, 10, 148)),
    ('Blue', (15, 117, 255)),
    ('Teal Green', (0, 147, 76)),
    ('Corn Flower Blue', (186, 189, 254)),
    ('Red', (236, 0, 0)),
    ('Reddish Brown', (228, 153, 90)),
    ('Magenta', (204, 72, 171)),
    ('Light Lilac', (253, 196, 250)),
    ('Lilac', (221, 132, 205)),
    ('Mint Green', (107, 211, 138)),
    ('Deep Gold', (228, 169, 69)),
    ('Orange', (255, 189, 66)),
    ('Yellow', (255, 230, 0)),
    ('Lime Green', (108, 217, 0)),
    ('Brass', (193, 169, 65)),
    ('Silver', (181, 173, 151)),
    ('Russet Brown', (186, 156, 95)),
    ('Cream Brown', (250, 245, 158)),
    ('Pewter', (128, 128, 128)),
    ('Black', (0, 0, 0)),
    ('Ultramarine', (0, 28, 223)),
    ('Royal Purple', (223, 0, 184)),
    ('Dark Gray', (98, 98, 98)),
    ('Dark Brown', (105, 38, 13)),
    ('Deep Rose', (255, 0, 96)),
    ('Light Brown', (191, 130, 0)),
    ('Salmon Pink', (243, 145, 120)),
    ('Vermilion', (255, 104, 5)),
    ('White', (240, 240, 240)),
    ('Violet', (200, 50, 205)),
    ('Seacrest', (176, 191, 155)),
    ('Sky Blue', (101, 191, 235)),
    ('Pumpkin', (255, 186, 4)),
    ('Cream Yellow', (255, 240, 108)),
    ('Khaki', (254, 202, 21)),
    ('Clay Brown', (243, 129, 1)),
    ('Leaf Green', (55, 169, 35)),
    ('Peacock Blue', (35, 70, 95)),
    ('Gray', (166, 166, 149)),
    ('Warm Gray', (206, 191, 166)),
    ('Dark Olive', (150, 170, 2)),
    ('Linen', (255, 227, 198)),
    ('Pink', (255, 153, 215)),
    ('Deep Green', (0, 112, 4)),
    ('Lavender', (237, 204, 251)),
    ('Wisteria Violet', (192, 137, 216)),
    ('Beige', (231, 217, 180)),
    ('Carmine', (233, 14, 134)),
    ('Amber Red', (207, 104, 41)),
    ('Olive Green', (64, 134, 21)),
    ('Dark Fuchsia', (219, 23, 151)),
    ('Tangerine', (255, 167, 4)),
    ('Light Blue', (185, 255, 255)),
    ('Emerald Green', (34, 137, 39)),
    ('Purple', (182, 18, 205)),
    ('Moss Green', (0, 170, 0)),
    ('Flesh Pink', (254, 169, 220)),
    ('Harvest Gold', (254, 213, 16)),
    ('Electric Blue', (0, 151, 223)),
    ('Lemon Yellow', (255, 255, 132)),
    ('Fresh Green', (207, 231, 116)),
    ('Applique Material', (255, 200, 100)),
    ('Applique Position', (255, 200, 200)),
    ('Applique', (255, 200, 200)),
]

PEC_HEADER_SIZE = 512
# Stitches start after the header, 2 zero bytes, the 3 byte stitch block
# length, 0x31 0xFF 0xF0 and four 16 bit values (width, height, 0x1E0, 0x1B0).
PEC_STITCH_OFFSET = PEC_HEADER_SIZE + 16

PREVIEW_SIZE = 512
PREVIEW_BACKGROUND = (226, 226, 226)


class PesError(ValueError):
    """The data is not a readable .pes file."""


def thread(index):
    """(name, '#rrggbb') of a PEC palette index."""
    if not 0 < index < len(PEC_THREADS):
        index = 0
    name, rgb = PEC_THREADS[index]
    return name, '#%02x%02x%02x' % rgb


class Design:
    """What a .pes file contains."""

    def __init__(self):
        self.version = ''
        self.label = ''
        self.stitch_count = 0
        self.jump_count = 0
        self.trim_count = 0
        # One entry per colour block, in stitching order:
        # {'index': palette index, 'name', 'hex', 'stitches': stitches in the block}
        self.colors = []
        self.width_mm = 0.0
        self.height_mm = 0.0
        # Per colour block, the polylines that were stitched (absolute 0.1 mm).
        self._paths = []
        self._extent = None

    @property
    def color_change_count(self):
        return max(len(self.colors) - 1, 0)

    def preview_png(self, size=PREVIEW_SIZE):
        """A PNG of the stitches drawn in their thread colours."""
        from PIL import Image, ImageDraw

        image = Image.new('RGB', (size, size), PREVIEW_BACKGROUND)
        if not self._extent:
            return _png(image)
        min_x, min_y, max_x, max_y = self._extent
        margin = size * 0.05
        span = max(max_x - min_x, max_y - min_y, 1)
        scale = (size - 2 * margin) / span
        offset_x = (size - (max_x - min_x) * scale) / 2
        offset_y = (size - (max_y - min_y) * scale) / 2
        line_width = max(1, round(size / 300))
        draw = ImageDraw.Draw(image)
        for color, paths in zip(self.colors, self._paths):
            rgb = tuple(int(color['hex'][i:i + 2], 16) for i in (1, 3, 5))
            for path in paths:
                points = [
                    (offset_x + (x - min_x) * scale, offset_y + (y - min_y) * scale)
                    for x, y in path
                ]
                if len(points) > 1:
                    draw.line(points, fill=rgb, width=line_width, joint='curve')
        return _png(image)


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _signed7(value):
    return value - 128 if value > 63 else value


def _signed12(value):
    value &= 0xFFF
    return value - 0x1000 if value > 0x7FF else value


def read_pes(data):
    """Read the bytes of a .pes file and return a :class:`Design`."""
    if len(data) < 12 or data[:4] != b'#PES':
        raise PesError('This is not a Brother .pes file.')
    pec_offset = struct.unpack_from('<I', data, 8)[0]
    design = read_pec(data, pec_offset)
    design.version = data[4:8].decode('ascii', 'replace')
    return design


def read_pec(data, offset=0):
    """Read a PEC section starting at ``offset`` of ``data``."""
    if offset + PEC_STITCH_OFFSET > len(data) or data[offset:offset + 3] != b'LA:':
        raise PesError('The .pes file has no readable stitch data.')
    design = Design()
    design.label = data[offset + 3:offset + 19].decode('latin-1').strip()
    color_indexes = list(data[offset + 49:offset + 49 + data[offset + 48] + 1])

    blocks = [[]]
    path = None
    x = y = 0
    min_x = min_y = max_x = max_y = None
    pos = offset + PEC_STITCH_OFFSET
    end = len(data)
    while pos + 1 < end:
        val1, val2 = data[pos], data[pos + 1]
        pos += 2
        if val1 == 0xFF and val2 == 0x00:
            break
        if val1 == 0xFE and val2 == 0xB0:
            pos += 1  # colour change marker byte
            blocks.append([])
            path = None
            continue
        jump = trim = False
        if val1 & 0x80:
            trim = trim or bool(val1 & 0x20)
            jump = jump or bool(val1 & 0x10)
            dx = _signed12((val1 << 8) | val2)
            if pos >= end:
                break
            val2 = data[pos]
            pos += 1
        else:
            dx = _signed7(val1)
        if val2 & 0x80:
            trim = trim or bool(val2 & 0x20)
            jump = jump or bool(val2 & 0x10)
            if pos >= end:
                break
            dy = _signed12((val2 << 8) | data[pos])
            pos += 1
        else:
            dy = _signed7(val2)

        x += dx
        y += dy
        if trim:
            design.trim_count += 1
        if jump or trim:
            design.jump_count += 1
            path = None
            continue
        points = [(x, y)]
        if path is None:
            # A new run of stitches starts where the needle was moved to.
            path = [(x - dx, y - dy)]
            blocks[-1].append(path)
            points.append(path[0])
        path.append((x, y))
        design.stitch_count += 1
        for px, py in points:
            if min_x is None:
                min_x = max_x = px
                min_y = max_y = py
            else:
                min_x, max_x = min(min_x, px), max(max_x, px)
                min_y, max_y = min(min_y, py), max(max_y, py)

    # A trailing colour change with no stitches after it isn't a real block.
    while len(blocks) > 1 and not blocks[-1]:
        blocks.pop()
    for number, paths in enumerate(blocks):
        index = color_indexes[number] if number < len(color_indexes) else 0
        name, hex_color = thread(index)
        design.colors.append({
            'index': index,
            'name': name,
            'hex': hex_color,
            'stitches': sum(len(p) - 1 for p in paths),
        })
    design._paths = blocks
    if min_x is not None:
        design._extent = (min_x, min_y, max_x, max_y)
        design.width_mm = (max_x - min_x) / 10.0
        design.height_mm = (max_y - min_y) / 10.0
    return design

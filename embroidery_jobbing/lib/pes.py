# -*- coding: utf-8 -*-
"""Read and write Brother .pes embroidery files.

A .pes file starts with "#PES" and a version, then the offset of its PEC
section. The PEC section is what Brother machines stitch from: a 512 byte
header (label, colour count and colour palette indexes) followed by the
stitch block. Coordinates are in 0.1 mm.

From version 5 the PES header also lists the real thread colours (name,
RGB, catalogue number and brand). :func:`read_pes` uses them when they are
there, and :func:`write_pes` writes version 6 files with them, so the
machine and Embrilliance show the thread actually used rather than the
nearest colour of Brother's palette. The layout follows pyembroidery
(MIT licence, https://github.com/EmbroidePy/pyembroidery).

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


# Stitch commands kept by the reader and taken by the writer:
# (x, y, kind) in absolute 0.1 mm, kind one of these.
STITCH = 'stitch'
JUMP = 'jump'
TRIM = 'trim'      # a jump that cuts the thread first
COLOR = 'color'    # change to the next thread


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
        # Every move in stitching order: (x, y, kind), see STITCH above.
        self.commands = []

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
    try:
        chart = _read_thread_chart(data, design.version)
    except (struct.error, IndexError, UnicodeDecodeError):
        chart = []  # an unusual header: the PEC palette colours still apply
    if chart:
        _apply_chart(design, chart)
    return design


# Bytes to skip in the PES header, per version, to reach the thread chart:
# (after the metadata strings, after the image file name).
_CHART_SKIPS = {
    '0050': (24, 24), '0055': (24, 24), '0056': (24, 24),
    '0060': (36, 24), '0070': (36, 24), '0080': (38, 26),
}


def _read_thread_chart(data, version):
    """The threads listed in a version 5 to 8 PES header, in chart order."""
    skips = _CHART_SKIPS.get(version)
    if not skips:
        return []
    pos = 12 + 4  # signature, PEC offset, hoop and 2 ascii digits

    def string():
        nonlocal pos
        length = data[pos]
        value = data[pos + 1:pos + 1 + length].decode('latin-1')
        pos += 1 + length
        return value

    for _metadata in range(5):  # name, category, author, keywords, comments
        string()
    pos += skips[0]
    string()  # image file name
    pos += skips[1]
    fills, motifs, feathers, count = struct.unpack_from('<4H', data, pos)
    pos += 8
    if fills or motifs or feathers:
        return []
    chart = []
    for _thread in range(count):
        catalog = string()
        red, green, blue = data[pos], data[pos + 1], data[pos + 2]
        pos += 3 + 5
        description = string()
        brand = string()
        string()  # chart name
        chart.append({
            'name': description or catalog or '#%02x%02x%02x' % (red, green, blue),
            'hex': '#%02x%02x%02x' % (red, green, blue),
            'catalog': catalog,
            'brand': brand,
        })
    return chart


def _apply_chart(design, chart):
    """Give the colour blocks the chart's threads the way Brother allocates
    them: one per block when the chart is long enough, else one per distinct
    PEC palette index in order of first use."""
    if len(chart) >= len(design.colors):
        threads = chart[:len(design.colors)]
    else:
        remaining = list(chart)
        by_index = {}
        threads = []
        for color in design.colors:
            if color['index'] not in by_index:
                by_index[color['index']] = remaining.pop(0) if remaining else None
            threads.append(by_index[color['index']])
    for color, chart_thread in zip(design.colors, threads):
        if chart_thread:
            color.update(chart_thread)


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
            design.commands.append((x, y, COLOR))
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
            design.commands.append((x, y, TRIM if trim else JUMP))
            continue
        design.commands.append((x, y, STITCH))
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
    # Drop a trailing colour change, as for the blocks above.
    while design.commands and design.commands[-1][2] == COLOR:
        design.commands.pop()
    if min_x is not None:
        design._extent = (min_x, min_y, max_x, max_y)
        design.width_mm = (max_x - min_x) / 10.0
        design.height_mm = (max_y - min_y) / 10.0
    return design


# ── Writing ───────────────────────────────────────────────────────────────

MAX_MOVE = 2000  # PEC moves are 12 bit signed: longer jumps are split
MAX_STITCH = 121  # 12.1 mm: Brother's longest stitch
PEC_ICON_STRIDE = 6  # bytes per row of the 48 x 38 monochrome icons
PEC_ICON_HEIGHT = 38


def _hex_rgb(value):
    value = (value or '#000000').lstrip('#')
    if len(value) != 6:
        return 0, 0, 0
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _nearest_pec(rgb, exclude=()):
    """Index of the PEC palette colour closest to ``rgb`` (red-mean distance)."""
    best, best_distance = 0, None
    for index, (_name, pec_rgb) in enumerate(PEC_THREADS):
        if not index or index in exclude:
            continue
        mean = (rgb[0] + pec_rgb[0]) / 2
        dr, dg, db = (rgb[i] - pec_rgb[i] for i in range(3))
        distance = (2 + mean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - mean) / 256) * db * db
        if best_distance is None or distance < best_distance:
            best, best_distance = index, distance
    return best


def write_pes(blocks, threads, label=''):
    """The bytes of a version 6 .pes file.

    ``blocks`` holds one list of (x, y, kind) commands per colour, in
    absolute 0.1 mm (kind STITCH, JUMP or TRIM), stitched in that order.
    ``threads`` holds one dict per block: ``name``, ``hex`` ('#rrggbb'), and
    optionally ``catalog`` (thread number) and ``brand``. The design is
    centred on the origin, as Brother machines expect.
    """
    if len(threads) != len(blocks):
        raise PesError('Each colour block needs a thread.')
    blocks = [[c for c in block if c[2] in (STITCH, JUMP, TRIM)] for block in blocks]
    pairs = [(block, thread) for block, thread in zip(blocks, threads)
             if any(c[2] == STITCH for c in block)]
    blocks = [pair[0] for pair in pairs]
    threads = [pair[1] for pair in pairs]
    points = [(c[0], c[1]) for block in blocks for c in block if c[2] == STITCH]
    if points:
        min_x = min(p[0] for p in points)
        max_x = max(p[0] for p in points)
        min_y = min(p[1] for p in points)
        max_y = max(p[1] for p in points)
    else:
        min_x = max_x = min_y = max_y = 0
    cx = round((min_x + max_x) / 2)
    cy = round((min_y + max_y) / 2)
    blocks = [[(round(x - cx), round(y - cy), kind) for x, y, kind in block] for block in blocks]
    blocks = _start_with_moves(blocks)
    extent = (min_x - cx, min_y - cy, max_x - cx, max_y - cy)

    # The chart lists each distinct thread once, in order of first use; each
    # distinct thread also gets its own PEC palette index (see _apply_chart).
    chart, chart_of_block = [], []
    for thread in threads:
        key = ((thread.get('hex') or '').lower(), thread.get('name') or '', thread.get('catalog') or '')
        keys = [k for k, _t in chart]
        if key not in keys:
            chart.append((key, thread))
            keys.append(key)
        chart_of_block.append(keys.index(key))
    pec_of_chart = []
    for _key, thread in chart:
        exclude = set(pec_of_chart) if len(pec_of_chart) < len(PEC_THREADS) - 1 else set()
        pec_of_chart.append(_nearest_pec(_hex_rgb(thread.get('hex')), exclude))
    pec_indexes = [pec_of_chart[i] for i in chart_of_block]

    out = bytearray(b'#PES0060')
    pec_offset_at = len(out)
    out += b'\x00\x00\x00\x00'
    _pes_header_v6(out, label, [t for _k, t in chart], 1 if points else 0)
    if points:
        out += struct.pack('<HH', 0xFFFF, 0)
        sections = _pes_blocks(out, blocks, chart_of_block, extent)
        out += struct.pack('<II', 0, 0)
        for number in range(sections):
            out += struct.pack('<II', number, 0)
    else:
        out += struct.pack('<HH', 0, 0)
    struct.pack_into('<I', out, pec_offset_at, len(out))
    _pec(out, label, blocks, pec_indexes, extent)
    # Addendum: the palette indexes again, then each chart colour.
    out += bytes(pec_of_chart[:128]) + b' ' * (128 - min(len(pec_of_chart), 128))
    out += b'\x00' * (0x90 * len(chart))
    for _key, thread in chart:
        red, green, blue = _hex_rgb(thread.get('hex'))
        out += bytes((blue, green, red))  # 24 bit little endian 0xRRGGBB
    out += b'\x00\x00'
    return bytes(out)


def _start_with_moves(blocks, longest=MAX_STITCH):
    """Move the needle (rather than stitch) to where each block starts, and
    turn any stitch too long for the machine into a move."""
    result = []
    x = y = 0
    for block in blocks:
        commands = []
        for cx, cy, kind in block:
            if kind == STITCH and not commands and (cx, cy) != (x, y):
                commands.append((cx, cy, TRIM if result else JUMP))
            elif kind == STITCH and max(abs(cx - x), abs(cy - y)) > longest:
                commands.append((cx, cy, TRIM))
            commands.append((cx, cy, kind))
            x, y = cx, cy
        result.append(commands)
    return result


def _pes_string(out, value, size=1):
    value = (value or '').encode('latin-1', 'replace')[:255]
    out += struct.pack('<B' if size == 1 else '<H', len(value)) + value


def _pes_header_v6(out, label, chart, objects):
    out += struct.pack('<H', 1) + b'02'
    _pes_string(out, label)
    for _empty in range(4):  # category, author, keywords, comments
        _pes_string(out, '')
    out += struct.pack(
        '<18H', 0, 0, 0x64, 0x64, 0, 0xC8, 0xC8, 0x64, 0x64, 0x64,
        0x07, 0x13, 0x01, 0x01, 0x00, 100, 0x01, 0x00,
    )
    out += b'\x00'  # no "from image" file name
    out += struct.pack('<6f', 1, 0, 0, 1, 0, 0)
    out += struct.pack('<4H', 0, 0, 0, len(chart))
    for thread in chart:
        red, green, blue = _hex_rgb(thread.get('hex'))
        _pes_string(out, thread.get('catalog') or '')
        out += bytes((red, green, blue, 0)) + struct.pack('<I', 0xA)  # 0xA: custom colour
        _pes_string(out, thread.get('name') or '')
        _pes_string(out, thread.get('brand') or '')
        _pes_string(out, '')  # chart name
    out += struct.pack('<H', objects)


def _segments(blocks, chart_of_block):
    """(flag, chart index, points) runs for the PES CSewSeg block: a run of
    stitches (flag 0) or a move from the last stitch to a new place (flag 1)."""
    x = y = 0
    for block, chart_index in zip(blocks, chart_of_block):
        run = []
        moving_from = None
        for cx, cy, kind in block:
            if kind == STITCH:
                if moving_from is not None:
                    yield 1, chart_index, [moving_from, (cx, cy)]
                    moving_from = None
                if not run or run[-1] != (cx, cy):
                    run.append((cx, cy))
            else:
                if len(run) > 1:
                    yield 0, chart_index, run
                if moving_from is None:
                    moving_from = (x, y)
                run = []
            x, y = cx, cy
        if len(run) > 1:
            yield 0, chart_index, run


def _pes_blocks(out, blocks, chart_of_block, extent):
    left, top, right, bottom = extent
    width, height = right - left, bottom - top
    _pes_string(out, 'CEmbOne', size=2)
    out += struct.pack('<8h', *([0] * 8))
    trans_x = 350 + 1300 / 2 - width / 2
    trans_y = 100 + height + 1800 / 2 - height / 2
    out += struct.pack('<6f', 1, 0, 0, 1, trans_x, trans_y)
    out += struct.pack('<5H', 1, 0, 0, int(width), int(height)) + b'\x00' * 8
    sections_at = len(out)
    out += b'\x00\x00'
    out += struct.pack('<HH', 0xFFFF, 0)
    _pes_string(out, 'CSewSeg', size=2)
    sections = 0
    color_log = []
    previous = None
    for flag, chart_index, points in _segments(blocks, chart_of_block):
        if sections:
            out += struct.pack('<H', 0x8003)
        if chart_index != previous:
            color_log.append((sections, chart_index))
            previous = chart_index
        out += struct.pack('<3H', flag, chart_index, len(points))
        for px, py in points:
            out += struct.pack('<hh', int(px - left), int(py - bottom))
        sections += 1
    out += struct.pack('<H', len(color_log))
    for section, chart_index in color_log:
        out += struct.pack('<HH', section, chart_index)
    struct.pack_into('<H', out, sections_at, sections)
    out += struct.pack('<HH', 0, 0)
    return len(color_log)


def _pec_value(value, long=False, flag=0):
    if not long and -64 < value < 63:
        return bytes([value & 0x7F])
    value = (value & 0x0FFF) | 0x8000 | (flag << 8)
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


def _pec(out, label, blocks, pec_indexes, extent):
    out += ('LA:%-16s\r' % (label or 'Untitled')[:8]).encode('latin-1', 'replace')
    out += b' ' * 12 + b'\xff\x00' + bytes([PEC_ICON_STRIDE, PEC_ICON_HEIGHT])
    if pec_indexes:
        out += b' ' * 12 + bytes([len(pec_indexes) - 1]) + bytes(pec_indexes)
    else:
        out += b'    \x64 \x00 \x00   \xff'
    out += b' ' * (463 - len(pec_indexes))

    start = len(out)
    left, top, right, bottom = extent
    out += b'\x00\x00\x00\x00\x00\x31\xff\xf0'
    out += struct.pack('<4H', int(round(right - left)), int(round(bottom - top)), 0x1E0, 0x1B0)
    x = y = 0
    first = True
    jumping = True
    for number, block in enumerate(blocks):
        if number:
            if jumping:
                out += _pec_value(0) + _pec_value(0)
                jumping = False
            out += b'\xfe\xb0' + (b'\x02' if number % 2 else b'\x01')
        for cx, cy, kind in block:
            if kind == STITCH:
                dx, dy = cx - x, cy - y
                if jumping:
                    if dx and dy:
                        out += _pec_value(0) + _pec_value(0)
                    jumping = False
                out += _pec_value(dx) + _pec_value(dy)
            else:
                jumping = True
                dx, dy = cx - x, cy - y
                flag = 0x10 if first else 0x20
                while True:
                    step_x = max(-MAX_MOVE, min(MAX_MOVE, dx))
                    step_y = max(-MAX_MOVE, min(MAX_MOVE, dy))
                    out += _pec_value(step_x, True, flag) + _pec_value(step_y, True, flag)
                    dx, dy = dx - step_x, dy - step_y
                    if not dx and not dy:
                        break
            x, y = cx, cy
            first = False
    out += b'\xff\x00'
    length = len(out) - start
    out[start + 2:start + 5] = struct.pack('<I', length)[:3]

    # Icons: the whole design, then one per colour block.
    everything = [(c[0], c[1]) for block in blocks for c in block if c[2] == STITCH]
    out += _pec_icon(everything, extent, 4)
    for block in blocks:
        out += _pec_icon([(c[0], c[1]) for c in block if c[2] == STITCH], extent, 5)


def _pec_icon(points, extent, margin):
    """A 48 x 38 one bit icon in Brother's rounded frame, with the points."""
    width, height = PEC_ICON_STRIDE * 8, PEC_ICON_HEIGHT
    icon = bytearray(PEC_ICON_STRIDE * height)

    def mark(px, py):
        if 0 <= px < width and 0 <= py < height:
            icon[py * PEC_ICON_STRIDE + px // 8] |= 1 << (px % 8)

    for px in range(4, width - 4):
        mark(px, 1)
        mark(px, height - 2)
    for py in range(2, height - 2):
        inset = 3 if py in (2, height - 3) else 2 if py in (3, height - 4) else 1
        mark(inset, py)
        mark(width - 1 - inset, py)
    left, top, right, bottom = extent
    scale = min((width - margin) / max(right - left, 1), (height - margin) / max(bottom - top, 1))
    offset_x = width / 2 - (left + right) / 2 * scale
    offset_y = height / 2 - (top + bottom) / 2 * scale
    for px, py in points:
        mark(int(px * scale + offset_x), int(py * scale + offset_y))
    return bytes(icon)

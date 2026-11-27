# -*- coding: utf-8 -*-
"""Turn artwork (PNG, JPG or SVG) into embroidery stitches.

1. The artwork is drawn at the stitched size, a fifth of a millimetre per
   pixel (coarser for very large designs).
2. The background is dropped: transparent pixels, and for opaque images
   the colour around the edge (flood filled from the border, so the same
   colour inside the design stays).
3. The colours are reduced, then each is matched to the nearest thread in
   the given catalogue (CIEDE2000 colour difference). Colours that land on
   the same thread are merged, and specks too small to stitch are given to
   the neighbouring colour.
4. Each thread colour, largest area first, is stitched as a tatami fill: an
   underlay at right angles, then rows 0.4 mm apart with the needle points
   staggered row by row. Rows are stitched back and forth in runs; a run
   that can't reach the next is ended with tie stitches and a trim.

The result is a list of colour blocks for :func:`pes.write_pes`. Only the
standard library and Pillow (plus lxml for SVG) are used.
"""
import io
import math
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import pes
from . import svg

ARTWORK_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.svg')
BACKGROUND_MARK = (255, 0, 254)


class DigitiseError(ValueError):
    """The artwork could not be digitised."""


class Settings:
    """How the artwork is digitised. Sizes are in millimetres."""

    def __init__(self, width_mm=80.0, height_mm=0.0, max_colors=6, row_spacing_mm=0.4,
                 stitch_length_mm=3.5, fill_angle=45.0, underlay=True,
                 remove_background=True, min_area_mm2=3.0):
        self.width_mm = float(width_mm or 0)
        self.height_mm = float(height_mm or 0)
        self.max_colors = max(1, min(int(max_colors or 1), 30))
        self.row_spacing_mm = max(0.25, float(row_spacing_mm or 0.4))
        self.stitch_length_mm = max(1.0, min(float(stitch_length_mm or 3.5), 7.0))
        self.fill_angle = float(fill_angle or 0) % 180
        self.underlay = bool(underlay)
        self.remove_background = bool(remove_background)
        self.min_area_mm2 = max(0.0, float(min_area_mm2 or 0))
        if self.width_mm <= 0 and self.height_mm <= 0:
            raise DigitiseError('Give the design a width or a height.')


class Result:
    """What :func:`digitise` made."""

    def __init__(self):
        self.blocks = []    # per thread colour: [(x, y, kind)] in 0.1 mm
        self.threads = []   # per block: the catalogue thread dict used
        self.colors = []    # per block: the artwork colour it stood for, '#rrggbb'
        self.width_mm = 0.0
        self.height_mm = 0.0

    def pes(self, label=''):
        return pes.write_pes(self.blocks, [dict(t) for t in self.threads], label=label)


# ── Colour matching ───────────────────────────────────────────────────────

def hex_to_rgb(value):
    value = (value or '').strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    if not re.fullmatch(r'[0-9a-fA-F]{6}', value):
        return None
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_lab(rgb):
    def linear(channel):
        channel /= 255.0
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(lab1, lab2):
    """CIEDE2000 colour difference: under 1 can't be seen, under 5 is close."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_mean = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_mean ** 7 / (c_mean ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dl = l2 - l1
    dc = c2p - c1p
    if c1p * c2p == 0:
        dh = 0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    dh_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_mean = (l1 + l2) / 2
    cp_mean = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_mean = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_mean = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_mean = (h1p + h2p + 360) / 2
    else:
        h_mean = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(h_mean - 30)) + 0.24 * math.cos(math.radians(2 * h_mean))
         + 0.32 * math.cos(math.radians(3 * h_mean + 6)) - 0.20 * math.cos(math.radians(4 * h_mean - 63)))
    d_theta = 30 * math.exp(-((h_mean - 275) / 25) ** 2)
    rc = 2 * math.sqrt(cp_mean ** 7 / (cp_mean ** 7 + 25 ** 7))
    sl = 1 + (0.015 * (l_mean - 50) ** 2) / math.sqrt(20 + (l_mean - 50) ** 2)
    sc = 1 + 0.045 * cp_mean
    sh = 1 + 0.015 * cp_mean * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dh_big / sh) ** 2
                     + rt * (dc / sc) * (dh_big / sh))


def brother_threads():
    """Brother's PEC palette as a thread catalogue, used when there is no other."""
    return [{'name': name, 'hex': '#%02x%02x%02x' % rgb, 'catalog': '', 'brand': 'Brother'}
            for name, rgb in pes.PEC_THREADS[1:]]


def nearest_thread(rgb, threads, shortlist=6):
    """(thread, colour difference) of the catalogue thread closest to ``rgb``.
    A plain Lab distance picks a shortlist, then CIEDE2000 decides."""
    lab = rgb_to_lab(rgb)
    candidates = []
    for thread in threads:
        if '_lab' not in thread:
            thread_rgb = hex_to_rgb(thread.get('hex'))
            if not thread_rgb:
                continue
            thread['_lab'] = rgb_to_lab(thread_rgb)
        t_lab = thread['_lab']
        candidates.append(((lab[0] - t_lab[0]) ** 2 + (lab[1] - t_lab[1]) ** 2
                           + (lab[2] - t_lab[2]) ** 2, len(candidates), thread))
    best, best_difference = None, None
    for _distance, _number, thread in sorted(candidates)[:shortlist]:
        difference = delta_e(lab, thread['_lab'])
        if best_difference is None or difference < best_difference:
            best, best_difference = thread, difference
    return best, best_difference


# ── Loading the artwork ───────────────────────────────────────────────────

def _target_size(natural_width, natural_height, settings):
    """(width mm, height mm) that keep the artwork's proportions within the
    settings' width and height (a 0 leaves that side free)."""
    ratio = natural_height / natural_width if natural_width else 1.0
    width, height = settings.width_mm, settings.height_mm
    if width > 0 and height > 0:
        if width * ratio > height:
            width = height / ratio
        else:
            height = width * ratio
    elif width > 0:
        height = width * ratio
    else:
        width = height / ratio
    return width, height


def load_artwork(data, filename, settings):
    """(RGBA image, mm per pixel, width mm, height mm) of the artwork drawn
    at its stitched size."""
    name = (filename or '').lower()
    is_svg = name.endswith('.svg') or data[:256].lstrip().startswith((b'<?xml', b'<svg'))
    if is_svg:
        try:
            root = svg.parse(data)
            _x, _y, natural_width, natural_height = svg.viewbox(root)
        except svg.SvgError as error:
            raise DigitiseError(str(error))
    else:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:
            raise DigitiseError('This is not a PNG, JPG or SVG image.')
        natural_width, natural_height = image.size
    width_mm, height_mm = _target_size(natural_width, natural_height, settings)
    if width_mm > 400 or height_mm > 400:
        raise DigitiseError('%.0f x %.0f mm is larger than any hoop. Make the design smaller.'
                            % (width_mm, height_mm))
    mm_per_px = max(0.2, max(width_mm, height_mm) / 1200.0)
    size = (max(1, round(width_mm / mm_per_px)), max(1, round(height_mm / mm_per_px)))
    if is_svg:
        try:
            image = svg.render(data, *size)
        except svg.SvgError as error:
            raise DigitiseError(str(error))
    else:
        if image.mode in ('P', 'LA', 'L', 'I', 'I;16', 'CMYK', '1', 'RGB'):
            image = image.convert('RGBA')
        elif image.mode != 'RGBA':
            image = image.convert('RGBA')
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image, mm_per_px, width_mm, height_mm


def _drop_background(image):
    """Make the opaque colour around the edge transparent (in place)."""
    width, height = image.size
    alpha = image.getchannel('A')
    transparent = sum(alpha.histogram()[:128])
    if transparent > width * height * 0.02:
        return  # the picture has its own transparent background
    # Work on a small copy: flood filling is slow on big images.
    scale = min(1.0, 300.0 / max(width, height))
    small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    small = image.convert('RGB').resize(small_size, Image.Resampling.NEAREST)
    small_pixels = small.load()
    sw, sh = small_size
    for x, y in [(x, 0) for x in range(sw)] + [(x, sh - 1) for x in range(sw)] \
            + [(0, y) for y in range(sh)] + [(sw - 1, y) for y in range(sh)]:
        if small_pixels[x, y] != BACKGROUND_MARK:
            ImageDraw.floodfill(small, (x, y), BACKGROUND_MARK, thresh=48)
    marked = Image.new('L', small_size, 0)
    marked.putdata([255 if p == BACKGROUND_MARK else 0 for p in small.getdata()])
    marked = marked.resize((width, height), Image.Resampling.NEAREST)
    keep = Image.eval(marked, lambda v: 0 if v else 255)
    image.putalpha(ImageChops.multiply(alpha, keep))


# ── Fills ─────────────────────────────────────────────────────────────────

def _rotate_back(angle, rotated_size, size):
    """A function mapping a point of the image rotated by ``angle`` degrees
    (PIL, expand=True) back to the unrotated image."""
    theta = math.radians(angle)
    cos, sin = math.cos(theta), math.sin(theta)
    rcx, rcy = rotated_size[0] / 2, rotated_size[1] / 2
    cx, cy = size[0] / 2, size[1] / 2

    def back(x, y):
        dx, dy = x - rcx, y - rcy
        return cx + dx * cos - dy * sin, cy + dx * sin + dy * cos

    return back


def fill_runs(mask, angle, spacing_px, stitch_px, stagger=True, min_run_px=2, max_link_px=12):
    """Tatami fill of a mask ('L', 255 = fill) as runs of needle points in
    the mask's pixels. Each run is stitched back and forth, row after row."""
    rotated = mask.rotate(angle, resample=Image.Resampling.NEAREST, expand=True)
    width, height = rotated.size
    data = rotated.tobytes()
    back = _rotate_back(angle, rotated.size, mask.size)
    rows = []
    y = spacing_px / 2
    while y < height:
        row = int(y)
        line = data[row * width:(row + 1) * width]
        rows.append((y, [(m.start(), m.end()) for m in re.finditer(rb'[\x80-\xff]+', line)
                         if m.end() - m.start() >= min_run_px]))
        y += spacing_px
    taken = [[False] * len(segments) for _y, segments in rows]
    runs = []
    for row_number, (_y, segments) in enumerate(rows):
        for seg_number in range(len(segments)):
            if taken[row_number][seg_number]:
                continue
            chain = [(row_number, seg_number)]
            taken[row_number][seg_number] = True
            forward = True
            current = segments[seg_number]
            next_row = row_number + 1
            while next_row < len(rows):
                end = current[1] if forward else current[0]
                found = None
                for number, candidate in enumerate(rows[next_row][1]):
                    if taken[next_row][number] or candidate[0] > current[1] or candidate[1] < current[0]:
                        continue
                    start = candidate[1] if forward else candidate[0]
                    if abs(start - end) <= max_link_px:
                        found = number
                    break
                if found is None:
                    break
                taken[next_row][found] = True
                chain.append((next_row, found))
                current = rows[next_row][1][found]
                forward = not forward
                next_row += 1
            runs.append(_run_points(chain, rows, stitch_px, stagger, back))
    return [run for run in runs if len(run) > 1]


def _run_points(chain, rows, stitch_px, stagger, back):
    points = []
    forward = True
    for row_number, seg_number in chain:
        y, segments = rows[row_number]
        x0, x1 = segments[seg_number]
        x0, x1 = x0 + 0.3, x1 - 0.3
        if x1 < x0:
            x0 = x1 = (x0 + x1) / 2
        offset = (row_number % 3) * stitch_px / 3 if stagger else 0
        inside = []
        k = math.ceil((x0 - offset) / stitch_px)
        while k * stitch_px + offset < x1:
            x = k * stitch_px + offset
            if x - x0 > stitch_px * 0.2 and x1 - x > stitch_px * 0.2:
                inside.append(x)
            k += 1
        row_points = [x0] + inside + [x1]
        if not forward:
            row_points.reverse()
        points.extend(back(x, y) for x in row_points)
        forward = not forward
    return points


# ── Stitching ─────────────────────────────────────────────────────────────

def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _order_runs(runs, start):
    """The runs in nearest-next order from ``start``, each possibly reversed."""
    ordered = []
    remaining = list(runs)
    position = start
    while remaining:
        best, best_distance, reverse = 0, None, False
        for number, run in enumerate(remaining):
            for flip, point in ((False, run[0]), (True, run[-1])):
                distance = _distance(position, point)
                if best_distance is None or distance < best_distance:
                    best, best_distance, reverse = number, distance, flip
        run = remaining.pop(best)
        if reverse:
            run = run[::-1]
        ordered.append(run)
        position = run[-1]
    return ordered


def _towards(a, b, length):
    distance = _distance(a, b)
    if not distance:
        return a
    t = min(1.0, length / distance)
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def stitch_runs(runs, start, tie=6, travel=20, longest=35):
    """Commands (0.1 mm) stitching the runs in order: short gaps are stitched
    across, longer ones are tied off, trimmed and tied in again."""
    commands = []
    position = start
    first = True
    for run in runs:
        if not run:
            continue
        if first or _distance(position, run[0]) > travel:
            if not first:
                back = _towards(position, commands[-2][:2] if len(commands) > 1 else position, tie)
                commands += [(back[0], back[1], pes.STITCH), (position[0], position[1], pes.STITCH)]
            commands.append((run[0][0], run[0][1], pes.JUMP if first else pes.TRIM))
            ahead = _towards(run[0], run[1] if len(run) > 1 else run[0], tie)
            commands += [(run[0][0], run[0][1], pes.STITCH), (ahead[0], ahead[1], pes.STITCH),
                         (run[0][0], run[0][1], pes.STITCH)]
        else:
            commands += _straight(position, run[0], longest)
        for previous, point in zip(run, run[1:]):
            commands += _straight(previous, point, longest)
        position = run[-1]
        first = False
    if commands:
        back = _towards(position, commands[-2][:2] if len(commands) > 1 else position, tie)
        commands += [(back[0], back[1], pes.STITCH), (position[0], position[1], pes.STITCH)]
    return commands


def _straight(a, b, longest):
    distance = _distance(a, b)
    if distance < 1:
        return []
    steps = max(1, math.ceil(distance / longest))
    return [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps, pes.STITCH)
            for i in range(1, steps + 1)]


# ── Putting it together ───────────────────────────────────────────────────

def digitise(data, filename, threads, settings=None):
    """Digitise artwork bytes into a :class:`Result`. ``threads`` is the
    catalogue to match (dicts with ``hex`` and ``name``, optionally
    ``catalog``, ``brand`` and any keys of your own, kept on the result);
    Brother's palette is used when it is empty."""
    settings = settings or Settings()
    threads = [dict(t) for t in threads if hex_to_rgb(t.get('hex'))] or brother_threads()
    image, mm_per_px, width_mm, height_mm = load_artwork(data, filename, settings)
    if settings.remove_background:
        _drop_background(image)
    opaque_mask = image.getchannel('A').point(lambda v: 255 if v >= 128 else 0)
    rgb = image.convert('RGB')

    # Colours of the opaque pixels, in buckets of 16 levels per channel.
    sample = [p[:3] for p in image.getdata() if p[3] >= 128]
    if not sample:
        raise DigitiseError('The artwork has nothing to stitch: it is empty or all background.')
    sample_image = Image.new('RGB', (len(sample), 1))
    sample_image.putdata(sample)
    buckets = {}
    for count, colour in sample_image.getcolors(maxcolors=len(sample) + 1):
        key = (colour[0] >> 4, colour[1] >> 4, colour[2] >> 4)
        bucket = buckets.setdefault(key, [0, 0, 0, 0])
        bucket[0] += count
        for channel in range(3):
            bucket[channel + 1] += colour[channel] * count

    # Each bucket goes to its nearest thread; buckets sharing a thread are one
    # colour. Keep the biggest up to the maximum number of colours and give
    # the rest to the kept colour they look most like.
    groups = {}
    for count, red, green, blue in buckets.values():
        colour = (red / count, green / count, blue / count)
        thread, _difference = nearest_thread(colour, threads)
        group = groups.setdefault(id(thread), {'thread': thread, 'pixels': 0, 'weighted': [0, 0, 0]})
        group['pixels'] += count
        group['weighted'] = [group['weighted'][0] + red, group['weighted'][1] + green,
                             group['weighted'][2] + blue]
    for group in groups.values():
        group['rgb'] = tuple(round(v / group['pixels']) for v in group['weighted'])
        group['lab'] = rgb_to_lab(group['rgb'])
    px_area = mm_per_px * mm_per_px
    ordered = sorted(groups.values(), key=lambda g: g['pixels'], reverse=True)
    kept = [g for g in ordered if g['pixels'] * px_area >= settings.min_area_mm2][:settings.max_colors] \
        or ordered[:1]
    for group in ordered:
        if group not in kept:
            target = min(kept, key=lambda k: delta_e(group['lab'], k['lab']))
            target['pixels'] += group['pixels']

    # Every pixel takes the kept colour nearest to it; the background is 255.
    palette = []
    for group in kept:
        palette += list(group['rgb'])
    palette += list(kept[0]['rgb']) * (256 - len(kept))
    palette_image = Image.new('P', (1, 1))
    palette_image.putpalette(palette)
    indexes = rgb.quantize(palette=palette_image, dither=Image.Dither.NONE)
    groups_image = Image.frombytes('L', image.size, indexes.tobytes())
    groups_image.paste(255, mask=Image.eval(opaque_mask, lambda v: 255 - v))
    # Smooth ragged edges and drop specks (majority of the neighbourhood).
    smooth = 3 if mm_per_px > 0.3 else 5
    groups_image = groups_image.filter(ImageFilter.ModeFilter(smooth))

    # Stitch each colour, largest first.
    result = Result()
    result.width_mm, result.height_mm = width_mm, height_mm
    to_units = mm_per_px * 10.0
    spacing_px = settings.row_spacing_mm / mm_per_px
    stitch_px = settings.stitch_length_mm / mm_per_px
    min_run_px = max(1, round(0.5 / mm_per_px))
    position = (0.0, 0.0)
    grow = max(1, round(0.2 / mm_per_px)) * 2 + 1  # overlap neighbours by about 0.2 mm
    shrink = max(1, round(0.6 / mm_per_px)) * 2 + 1  # keep underlay 0.6 mm inside
    for number, group in enumerate(kept):
        mask = groups_image.point([255 if v == number else 0 for v in range(256)])
        if not mask.getbbox():
            continue
        top_mask = mask.filter(ImageFilter.MaxFilter(grow)) if grow > 1 else mask
        runs = []
        if settings.underlay:
            under_mask = mask.filter(ImageFilter.MinFilter(shrink))
            if under_mask.getbbox():
                runs += _order_runs(fill_runs(under_mask, settings.fill_angle + 90, 2.0 / mm_per_px,
                                              3.0 / mm_per_px, stagger=False, min_run_px=min_run_px,
                                              max_link_px=2.5 / mm_per_px),
                                    (position[0] / to_units, position[1] / to_units))
        top = fill_runs(top_mask, settings.fill_angle, spacing_px, stitch_px, stagger=True,
                        min_run_px=min_run_px, max_link_px=2.0 / mm_per_px)
        if not top:
            continue
        start = runs[-1][-1] if runs else (position[0] / to_units, position[1] / to_units)
        runs += _order_runs(top, start)
        runs = [[(x * to_units, y * to_units) for x, y in run] for run in runs]
        commands = stitch_runs(runs, position, longest=round(settings.stitch_length_mm * 10) + 1)
        if not commands:
            continue
        position = commands[-1][:2]
        result.blocks.append(commands)
        thread = {k: v for k, v in group['thread'].items() if k != '_lab'}
        result.threads.append(thread)
        result.colors.append('#%02x%02x%02x' % group['rgb'])
    if not result.blocks:
        raise DigitiseError('The artwork has no area large enough to stitch.')
    return result

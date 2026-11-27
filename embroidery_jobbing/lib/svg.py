# -*- coding: utf-8 -*-
"""Draw an SVG file onto a Pillow image, for digitising.

Embroidery only needs the flat coloured shapes of a logo or drawing, so
this covers what logo files use: paths (every command, arcs included),
rect, circle, ellipse, line, polyline and polygon, groups with transforms,
<use>, fill and stroke colours (attributes, style="...", and simple
<style> rules by tag, class or id), gradients as their average colour,
evenodd and nonzero fill rules. Text must be converted to outlines first
(e.g. "Create Outlines" / "Object to Path"). Shapes are drawn without
anti-aliasing so each colour stays one clean region.

Only the standard library, lxml and Pillow are used.
"""
import math
import re

from lxml import etree
from PIL import Image, ImageChops, ImageColor, ImageDraw

SVG_NS = '{http://www.w3.org/2000/svg}'
XLINK_HREF = '{http://www.w3.org/1999/xlink}href'

SKIPPED = {'defs', 'clipPath', 'mask', 'symbol', 'title', 'desc', 'metadata', 'style',
           'text', 'pattern', 'marker', 'linearGradient', 'radialGradient', 'filter',
           'script', 'foreignObject', 'image', 'switch'}
INHERITED = ('fill', 'stroke', 'stroke-width', 'fill-rule', 'fill-opacity',
             'stroke-opacity', 'color', 'visibility', '_opacity')
UNITS = {'px': 1.0, 'pt': 4 / 3, 'pc': 16.0, 'mm': 96 / 25.4, 'cm': 96 / 2.54, 'in': 96.0}


class SvgError(ValueError):
    """The data is not an SVG file that can be drawn."""


def _length(value, default=0.0, reference=0.0):
    if value is None:
        return default
    match = re.match(r'\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)\s*([a-z%]*)', str(value))
    if not match:
        return default
    number, unit = float(match.group(1)), match.group(2)
    if unit == '%':
        return number / 100.0 * reference
    return number * UNITS.get(unit, 1.0)


# ── Transforms (a, b, c, d, e, f as in SVG's matrix()) ────────────────────

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2,
            b * c2 + d * d2, a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def _apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _numbers(text):
    return [float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?', text or '')]


def parse_transform(text):
    matrix = IDENTITY
    for name, args in re.findall(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)', text or ''):
        v = _numbers(args)
        if name == 'matrix' and len(v) == 6:
            step = tuple(v)
        elif name == 'translate' and v:
            step = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale' and v:
            step = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == 'rotate' and v:
            angle = math.radians(v[0])
            cos, sin = math.cos(angle), math.sin(angle)
            step = (cos, sin, -sin, cos, 0, 0)
            if len(v) == 3:
                step = _multiply(_multiply((1, 0, 0, 1, v[1], v[2]), step), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == 'skewX' and v:
            step = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == 'skewY' and v:
            step = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        matrix = _multiply(matrix, step)
    return matrix


# ── Path data ─────────────────────────────────────────────────────────────

class _PathReader:
    NUMBER = re.compile(r'\s*,?\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)')
    FLAG = re.compile(r'\s*,?\s*([01])')
    COMMAND = re.compile(r'\s*,?\s*([MmZzLlHhVvCcSsQqTtAa])')

    def __init__(self, text):
        self.text = text or ''
        self.pos = 0

    def command(self):
        match = self.COMMAND.match(self.text, self.pos)
        if not match:
            return None
        self.pos = match.end()
        return match.group(1)

    def has_number(self):
        return bool(self.NUMBER.match(self.text, self.pos))

    def number(self):
        match = self.NUMBER.match(self.text, self.pos)
        if not match:
            raise SvgError('Bad path data near "%s"' % self.text[self.pos:self.pos + 20])
        self.pos = match.end()
        return float(match.group(1))

    def flag(self):
        match = self.FLAG.match(self.text, self.pos)
        if not match:
            raise SvgError('Bad arc flag near "%s"' % self.text[self.pos:self.pos + 20])
        self.pos = match.end()
        return match.group(1) == '1'


def _bezier(points, steps):
    """Points along a quadratic or cubic Bézier (excluding the start)."""
    result = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        if len(points) == 3:
            (x0, y0), (x1, y1), (x2, y2) = points
            result.append((mt * mt * x0 + 2 * mt * t * x1 + t * t * x2,
                           mt * mt * y0 + 2 * mt * t * y1 + t * t * y2))
        else:
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
            result.append((mt ** 3 * x0 + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t ** 3 * x3,
                           mt ** 3 * y0 + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t ** 3 * y3))
    return result


def _steps(points, scale):
    length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)) * scale
    return max(4, min(64, int(length / 3)))


def _arc(x1, y1, rx, ry, angle, large, sweep, x2, y2, scale):
    """Points along an SVG elliptical arc (spec F.6.5), excluding the start."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [(x2, y2)]
    phi = math.radians(angle)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = cos * dx + sin * dy, -sin * dx + cos * dy
    scale_r = (xp * xp) / (rx * rx) + (yp * yp) / (ry * ry)
    if scale_r > 1:
        rx, ry = rx * math.sqrt(scale_r), ry * math.sqrt(scale_r)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    factor = math.sqrt(max(num / den, 0)) if den else 0
    if large == sweep:
        factor = -factor
    cxp, cyp = factor * rx * yp / ry, -factor * ry * xp / rx
    cx = cos * cxp - sin * cyp + (x1 + x2) / 2
    cy = sin * cxp + cos * cyp + (y1 + y2) / 2

    def angle_of(ux, uy, vx, vy):
        value = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return value

    start = angle_of(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    delta = angle_of((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(4, min(96, int(abs(delta) * max(rx, ry) * scale / 3)))
    points = []
    for i in range(1, steps + 1):
        theta = start + delta * i / steps
        ex, ey = rx * math.cos(theta), ry * math.sin(theta)
        points.append((cos * ex - sin * ey + cx, sin * ex + cos * ey + cy))
    return points


def parse_path(text, scale=1.0):
    """The subpaths of SVG path data, as lists of (x, y), and whether each is
    closed. ``scale`` (output pixels per unit) sets how finely curves are cut."""
    reader = _PathReader(text)
    subpaths = []
    current = None
    x = y = start_x = start_y = 0.0
    last_control = None
    last_command = ''
    command = reader.command()
    while command:
        relative = command.islower()
        upper = command.upper()
        if upper == 'Z':
            if current:
                subpaths.append((current, True))
            current = None
            x, y = start_x, start_y
            last_command = 'Z'
            command = reader.command()
            continue
        first = True
        while first or reader.has_number():
            ox, oy = (x, y) if relative else (0.0, 0.0)
            if upper == 'M':
                x, y = reader.number() + ox, reader.number() + oy
                if first:
                    if current and len(current) > 1:
                        subpaths.append((current, False))
                    current = [(x, y)]
                    start_x, start_y = x, y
                    upper_after = 'L'
                else:
                    current.append((x, y))
                    upper_after = 'L'
                last_control = None
            else:
                if current is None:
                    current = [(x, y)]
                    start_x, start_y = x, y
                if upper == 'L':
                    x, y = reader.number() + ox, reader.number() + oy
                    current.append((x, y))
                    last_control = None
                elif upper == 'H':
                    x = reader.number() + ox
                    current.append((x, y))
                    last_control = None
                elif upper == 'V':
                    y = reader.number() + oy
                    current.append((x, y))
                    last_control = None
                elif upper in ('C', 'S'):
                    if upper == 'C':
                        c1 = (reader.number() + ox, reader.number() + oy)
                    elif last_control and last_command in ('C', 'S'):
                        c1 = (2 * x - last_control[0], 2 * y - last_control[1])
                    else:
                        c1 = (x, y)
                    c2 = (reader.number() + ox, reader.number() + oy)
                    end = (reader.number() + ox, reader.number() + oy)
                    curve = [(x, y), c1, c2, end]
                    current.extend(_bezier(curve, _steps(curve, scale)))
                    last_control = c2
                    x, y = end
                elif upper in ('Q', 'T'):
                    if upper == 'Q':
                        c1 = (reader.number() + ox, reader.number() + oy)
                    elif last_control and last_command in ('Q', 'T'):
                        c1 = (2 * x - last_control[0], 2 * y - last_control[1])
                    else:
                        c1 = (x, y)
                    end = (reader.number() + ox, reader.number() + oy)
                    curve = [(x, y), c1, end]
                    current.extend(_bezier(curve, _steps(curve, scale)))
                    last_control = c1
                    x, y = end
                elif upper == 'A':
                    rx, ry, angle = reader.number(), reader.number(), reader.number()
                    large, sweep = reader.flag(), reader.flag()
                    end = (reader.number() + ox, reader.number() + oy)
                    current.extend(_arc(x, y, rx, ry, angle, large, sweep, end[0], end[1], scale))
                    x, y = end
                    last_control = None
            last_command = upper
            first = False
            if upper == 'M':
                upper = upper_after  # numbers after a moveto are linetos
        command = reader.command()
    if current and len(current) > 1:
        subpaths.append((current, False))
    return subpaths


def _ellipse(cx, cy, rx, ry, scale):
    steps = max(12, min(180, int(2 * math.pi * max(rx, ry) * scale / 3)))
    return [(cx + rx * math.cos(2 * math.pi * i / steps), cy + ry * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


# ── Styles ────────────────────────────────────────────────────────────────

def _parse_css(text):
    """{('tag'|'class'|'id', name): {property: value}} from simple <style> rules."""
    rules = {}
    text = re.sub(r'/\*.*?\*/', '', text or '', flags=re.S)
    for selectors, body in re.findall(r'([^{}]+)\{([^}]*)\}', text):
        declarations = _parse_style(body)
        for selector in selectors.split(','):
            selector = selector.strip()
            if re.fullmatch(r'\.[\w-]+', selector):
                key = ('class', selector[1:])
            elif re.fullmatch(r'#[\w-]+', selector):
                key = ('id', selector[1:])
            elif re.fullmatch(r'[\w-]+', selector):
                key = ('tag', selector)
            else:
                continue
            rules.setdefault(key, {}).update(declarations)
    return rules


def _parse_style(text):
    result = {}
    for part in (text or '').split(';'):
        if ':' in part:
            name, value = part.split(':', 1)
            result[name.strip()] = value.replace('!important', '').strip()
    return result


class _Renderer:

    def __init__(self, root, width, height):
        self.root = root
        self.ids = {el.get('id'): el for el in root.iter() if isinstance(el.tag, str) and el.get('id')}
        self.css = {}
        for style in root.iter(SVG_NS + 'style', 'style'):
            for key, value in _parse_css(style.text).items():
                self.css.setdefault(key, {}).update(value)
        self.gradients = {}
        for el in root.iter():
            if isinstance(el.tag, str) and _tag(el) in ('linearGradient', 'radialGradient') and el.get('id'):
                self.gradients[el.get('id')] = el
        self.image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        self.depth = 0

    def style_of(self, el, inherited):
        style = {name: inherited[name] for name in INHERITED if name in inherited}
        for name in INHERITED + ('opacity', 'display'):
            if el.get(name) is not None:
                style[name] = el.get(name)
        for key in [('tag', _tag(el))] + [('class', c) for c in (el.get('class') or '').split()] \
                + [('id', el.get('id'))]:
            style.update(self.css.get(key, {}))
        style.update(_parse_style(el.get('style')))
        own = _numbers(el.get('opacity') or _parse_style(el.get('style')).get('opacity') or '1')
        style['_opacity'] = float(inherited.get('_opacity', 1.0)) * (own[0] if own else 1.0)
        return style

    def colour(self, value, style, opacity_name):
        value = (value or '').strip()
        if not value or value == 'none' or value == 'transparent':
            return None
        opacity = float(style.get('_opacity', 1.0))
        own = _numbers(style.get(opacity_name, '1'))
        if own:
            opacity *= own[0]
        if opacity < 0.2:
            return None
        if value.startswith('url('):
            match = re.match(r'url\(\s*["\']?#([^)"\']+)', value)
            return self.gradient_colour(match.group(1) if match else None)
        if value == 'currentColor':
            value = style.get('color') or '#000000'
        try:
            rgb = ImageColor.getrgb(value)
        except ValueError:
            return None
        if len(rgb) == 4 and rgb[3] < 51:
            return None
        return rgb[:3]

    def gradient_colour(self, gradient_id, seen=()):
        el = self.gradients.get(gradient_id)
        if el is None or gradient_id in seen:
            return None
        stops = [s for s in el if isinstance(s.tag, str) and _tag(s) == 'stop']
        if not stops:
            href = el.get(XLINK_HREF) or el.get('href') or ''
            return self.gradient_colour(href.lstrip('#'), seen + (gradient_id,))
        colours = []
        for stop in stops:
            style = _parse_style(stop.get('style'))
            value = style.get('stop-color') or stop.get('stop-color') or '#000000'
            try:
                colours.append(ImageColor.getrgb(value)[:3])
            except ValueError:
                continue
        if not colours:
            return None
        return tuple(round(sum(c[i] for c in colours) / len(colours)) for i in range(3))

    def render(self, el, matrix, inherited):
        if not isinstance(el.tag, str):
            return
        tag = _tag(el)
        if tag in SKIPPED:
            return
        style = self.style_of(el, inherited)
        if style.get('display') == 'none':
            return
        matrix = _multiply(matrix, parse_transform(el.get('transform')))
        if tag in ('svg', 'g', 'a'):
            if tag == 'svg' and el is not self.root:
                matrix = _multiply(matrix, (1, 0, 0, 1, _length(el.get('x')), _length(el.get('y'))))
            for child in el:
                self.render(child, matrix, style)
            return
        if tag == 'use':
            href = (el.get(XLINK_HREF) or el.get('href') or '').lstrip('#')
            target = self.ids.get(href)
            if target is not None and self.depth < 8:
                self.depth += 1
                moved = _multiply(matrix, (1, 0, 0, 1, _length(el.get('x')), _length(el.get('y'))))
                if _tag(target) == 'symbol':
                    for child in target:
                        self.render(child, moved, style)
                else:
                    self.render(target, moved, style)
                self.depth -= 1
            return
        if style.get('visibility') in ('hidden', 'collapse'):
            return
        scale = math.sqrt(abs(matrix[0] * matrix[3] - matrix[1] * matrix[2])) or 1.0
        subpaths = self.shape(el, tag, scale)
        if not subpaths:
            return
        fill = self.colour(style.get('fill', '#000000'), style, 'fill-opacity')
        stroke = self.colour(style.get('stroke'), style, 'stroke-opacity')
        transformed = [([_apply(matrix, px, py) for px, py in points], closed) for points, closed in subpaths]
        if fill and tag != 'line':
            self.fill(transformed, fill, style.get('fill-rule', 'nonzero'))
        if stroke:
            width = _length(style.get('stroke-width'), 1.0) * scale
            self.stroke(transformed, stroke, width)

    def shape(self, el, tag, scale):
        get = lambda name, default=0.0: _length(el.get(name), default)
        if tag == 'path':
            return parse_path(el.get('d'), scale)
        if tag == 'rect':
            x, y, w, h = get('x'), get('y'), get('width'), get('height')
            if w <= 0 or h <= 0:
                return []
            rx = get('rx', -1)
            ry = get('ry', -1)
            rx = ry if rx < 0 else rx
            ry = rx if ry < 0 else ry
            rx, ry = min(max(rx, 0), w / 2), min(max(ry, 0), h / 2)
            if not rx or not ry:
                return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
            points = []
            for cx, cy, start in ((x + w - rx, y + ry, -90), (x + w - rx, y + h - ry, 0),
                                  (x + rx, y + h - ry, 90), (x + rx, y + ry, 180)):
                for i in range(0, 91, 10):
                    angle = math.radians(start + i)
                    points.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
            return [(points, True)]
        if tag == 'circle':
            r = get('r')
            return [(_ellipse(get('cx'), get('cy'), r, r, scale), True)] if r > 0 else []
        if tag == 'ellipse':
            rx, ry = get('rx'), get('ry')
            return [(_ellipse(get('cx'), get('cy'), rx, ry, scale), True)] if rx > 0 and ry > 0 else []
        if tag == 'line':
            return [([(get('x1'), get('y1')), (get('x2'), get('y2'))], False)]
        if tag in ('polyline', 'polygon'):
            values = _numbers(el.get('points'))
            points = list(zip(values[0::2], values[1::2]))
            return [(points, tag == 'polygon')] if len(points) > 1 else []
        return []

    def fill(self, subpaths, colour, rule):
        polygons = [points for points, _closed in subpaths if len(points) > 2]
        if not polygons:
            return
        box = _bounds(polygons, self.image.size)
        if not box:
            return
        left, top, right, bottom = box
        size = (right - left, bottom - top)
        mask = Image.new('1', size, 0)
        shifted = [[(px - left, py - top) for px, py in points] for points in polygons]
        if rule == 'evenodd' or len(shifted) == 1:
            for points in shifted:
                layer = Image.new('1', size, 0)
                ImageDraw.Draw(layer).polygon(points, fill=1)
                mask = _xor(mask, layer)
        else:
            # nonzero: biggest first; a subpath wound the other way from the
            # outline cuts a hole, one wound the same way adds to it.
            ordered = sorted(shifted, key=lambda p: abs(_area(p)), reverse=True)
            outer = _area(ordered[0]) >= 0
            for points in ordered:
                layer = Image.new('1', size, 0)
                ImageDraw.Draw(layer).polygon(points, fill=1)
                if (_area(points) >= 0) == outer:
                    mask = _or(mask, layer)
                else:
                    mask = _subtract(mask, layer)
        self.image.paste(colour + (255,), (left, top), mask.convert('L'))

    def stroke(self, subpaths, colour, width):
        width = max(1, int(round(width)))
        draw = ImageDraw.Draw(self.image)
        for points, closed in subpaths:
            if closed:
                points = points + points[:1]
            if len(points) > 1:
                draw.line(points, fill=colour + (255,), width=width, joint='curve')
                if width > 2:
                    for px, py in (points[0], points[-1]):
                        draw.ellipse((px - width / 2, py - width / 2, px + width / 2, py + width / 2),
                                     fill=colour + (255,))


def _xor(a, b):
    return ImageChops.logical_xor(a, b)


def _or(a, b):
    return ImageChops.logical_or(a, b)


def _subtract(a, b):
    return ImageChops.logical_and(a, ImageChops.invert(b.convert('L')).convert('1'))


def _area(points):
    return sum(points[i][0] * points[i - 1][1] - points[i - 1][0] * points[i][1]
               for i in range(len(points))) / 2


def _bounds(polygons, size):
    xs = [p[0] for points in polygons for p in points]
    ys = [p[1] for points in polygons for p in points]
    left, top = max(int(math.floor(min(xs))) - 1, 0), max(int(math.floor(min(ys))) - 1, 0)
    right, bottom = min(int(math.ceil(max(xs))) + 2, size[0]), min(int(math.ceil(max(ys))) + 2, size[1])
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _tag(el):
    return el.tag.rsplit('}', 1)[-1]


def parse(data):
    """The root element of SVG data (entities and network access disabled)."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as error:
        raise SvgError('This is not a readable SVG file (%s).' % error)
    if _tag(root) != 'svg':
        raise SvgError('This is not an SVG file.')
    return root


def viewbox(root):
    """(min x, min y, width, height) of the drawing in user units."""
    values = _numbers(root.get('viewBox'))
    if len(values) == 4 and values[2] > 0 and values[3] > 0:
        return tuple(values)
    width = _length(root.get('width'), 0)
    height = _length(root.get('height'), 0)
    if width > 0 and height > 0:
        return 0.0, 0.0, width, height
    raise SvgError('The SVG file has no size: give it a viewBox or a width and height.')


def render(data, width, height):
    """An RGBA image of the SVG, stretched to ``width`` x ``height`` pixels
    (keep the viewBox proportions to avoid distortion)."""
    root = parse(data)
    min_x, min_y, box_width, box_height = viewbox(root)
    renderer = _Renderer(root, width, height)
    matrix = (width / box_width, 0, 0, height / box_height,
              -min_x * width / box_width, -min_y * height / box_height)
    style = {'fill': '#000000'}
    for child in root:
        renderer.render(child, matrix, renderer.style_of(root, style))
    return renderer.image

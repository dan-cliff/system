# -*- coding: utf-8 -*-
"""Build the .svg file of cutting and scoring jobs.

Uploaded SVGs (template bases and customer artwork) are parsed without
entities or network access and stripped of anything active (scripts, event
handlers, external references), so they are safe to show in a browser and to
embed in a job's file.

Coordinates are in millimetres: the file's viewBox is the template's size in
mm, and its width/height say "mm", so laser software imports it at the right
size. Text is turned into outlines when the element's font has a font file
and the fontTools library is installed (the laser then cuts or scores the
letters' shapes); otherwise it stays <text> in the font's family.
"""
import copy
import io
import re

from lxml import etree

try:  # Optional: outlines text so the file doesn't depend on installed fonts.
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover - depends on the server
    TTFont = None

SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'
NSMAP = {None: SVG_NS, 'xlink': XLINK_NS}

LINE_HEIGHT = 1.2
STROKE_WIDTH_MM = 0.1

FORBIDDEN_TAGS = {
    'script', 'foreignObject', 'iframe', 'embed', 'object', 'audio', 'video', 'canvas',
    'animate', 'set', 'animateMotion', 'animateTransform', 'handler', 'listener',
}
SAFE_DATA_HREF = re.compile(r'^\s*data:image/(png|jpe?g|gif|webp|bmp);base64,', re.I)
EXTERNAL_URL = re.compile(r'url\(\s*[\'"]?\s*(?!#)', re.I)
DANGEROUS_CSS = re.compile(r'(@import|javascript:|expression\s*\(|behavior\s*:)', re.I)
LENGTH = re.compile(r'^\s*([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*(mm|cm|in|pt|pc|px)?\s*$')
COLOR = re.compile(r'^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$')
# User units (px at 96 dpi) per unit.
UNIT_PX = {None: 1.0, 'px': 1.0, 'mm': 96 / 25.4, 'cm': 96 / 2.54, 'in': 96.0, 'pt': 96 / 72, 'pc': 16.0}


class SvgError(ValueError):
    """The SVG can't be read."""


def q(tag):
    return '{%s}%s' % (SVG_NS, tag)


def safe_color(value, default='#000000'):
    value = (value or '').strip()
    return value if COLOR.match(value) else default


# ─────────────────────────────────────────────────────────────────────────────
# Reading and cleaning
# ─────────────────────────────────────────────────────────────────────────────

def parse_svg(data):
    """Parse and sanitise an SVG; return its root element."""
    if isinstance(data, str):
        data = data.encode()
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False,
        remove_comments=True, remove_pis=True, huge_tree=False,
    )
    try:
        root = etree.fromstring(data, parser)
    except (etree.XMLSyntaxError, ValueError) as error:
        raise SvgError('The SVG file could not be read (%s).' % error) from error
    if root is None or not isinstance(root.tag, str) or etree.QName(root).localname != 'svg':
        raise SvgError('This file is not an SVG image.')
    sanitize(root)
    return root


def sanitize(root):
    """Remove scripts, event handlers and external references, in place."""
    for element in list(root.iter()):
        if element is root:
            continue
        if not isinstance(element.tag, str):  # entity references and the like
            _drop(element)
            continue
        name = etree.QName(element).localname
        if name in FORBIDDEN_TAGS:
            _drop(element)
            continue
        if name == 'style' and element.text and (
            DANGEROUS_CSS.search(element.text) or EXTERNAL_URL.search(element.text)
        ):
            _drop(element)
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attribute in list(element.attrib):
            local = etree.QName(attribute).localname.lower()
            value = element.attrib[attribute]
            if local.startswith('on'):
                del element.attrib[attribute]
            elif local == 'href' and not (value.strip().startswith('#') or SAFE_DATA_HREF.match(value)):
                del element.attrib[attribute]
            elif local == 'style' and (DANGEROUS_CSS.search(value) or EXTERNAL_URL.search(value)):
                del element.attrib[attribute]
            elif EXTERNAL_URL.search(value) and 'url(' in value.lower():
                del element.attrib[attribute]
    return root


def _drop(element):
    parent = element.getparent()
    if parent is not None:
        # Keep the text that followed the removed element.
        if element.tail:
            previous = element.getprevious()
            if previous is not None:
                previous.tail = (previous.tail or '') + element.tail
            else:
                parent.text = (parent.text or '') + element.tail
        parent.remove(element)


def sanitized_svg(data):
    """The sanitised SVG as bytes, ready to serve to a browser."""
    return etree.tostring(parse_svg(data), xml_declaration=True, encoding='UTF-8')


def parse_length(value):
    """A width/height in user units (px at 96 dpi); None for % or missing."""
    match = LENGTH.match(value or '')
    if not match:
        return None
    return float(match.group(1)) * UNIT_PX[match.group(2)]


def view_box(root):
    """(x, y, width, height) of an SVG's drawing, in its user units."""
    box = root.get('viewBox')
    if box:
        try:
            parts = [float(p) for p in re.split(r'[\s,]+', box.strip())]
        except ValueError:
            parts = []
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return tuple(parts)
    width, height = parse_length(root.get('width')), parse_length(root.get('height'))
    if width and height:
        return (0.0, 0.0, width, height)
    raise SvgError('The SVG has no size: give it a viewBox or a width and height.')


def size_mm(root):
    """(width, height) in mm when the SVG states absolute dimensions, else None."""
    width, height = parse_length(root.get('width')), parse_length(root.get('height'))
    if width and height:
        return (width / UNIT_PX['mm'], height / UNIT_PX['mm'])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Building
# ─────────────────────────────────────────────────────────────────────────────

def fit_transform(source, target, mode='contain'):
    """SVG transform placing the source box (x, y, w, h) in the target box."""
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    scale = (max if mode == 'cover' else min)(tw / sw, th / sh)
    dx = tx + (tw - sw * scale) / 2 - sx * scale
    dy = ty + (th - sh * scale) / 2 - sy * scale
    return 'translate(%s %s) scale(%s)' % (_num(dx), _num(dy), _num(scale, 6))


def _num(value, digits=4):
    text = ('%.*f' % (digits, value)).rstrip('0').rstrip('.')
    return '0' if text in ('', '-0') else text


ID_REF = re.compile(r'url\(\s*([\'"]?)#([^)\'"\s]+)\1\s*\)')


def prefix_ids(root, prefix):
    """Give every id in an embedded SVG a prefix so several can share a file."""
    ids = {el.get('id') for el in root.iter() if isinstance(el.tag, str) and el.get('id')}
    if not ids:
        return

    def fix_refs(text):
        return ID_REF.sub(
            lambda m: 'url(%s#%s%s%s)' % (m.group(1), prefix if m.group(2) in ids else '', m.group(2), m.group(1)),
            text,
        )

    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attribute, value in list(element.attrib.items()):
            local = etree.QName(attribute).localname
            if local == 'id' and value in ids:
                element.set(attribute, prefix + value)
            elif local == 'href' and value.startswith('#') and value[1:] in ids:
                element.set(attribute, '#' + prefix + value[1:])
            elif 'url(' in value:
                element.set(attribute, fix_refs(value))
        if etree.QName(element).localname == 'style' and element.text:
            element.text = fix_refs(element.text)
            for old in ids:
                element.text = re.sub(r'#%s\b' % re.escape(old), '#' + prefix + old, element.text)


def embed_svg(parent, defs, source_root, box, mode='contain', prefix='e', clip=False):
    """Copy an SVG's drawing into parent, scaled into box (x, y, w, h) in mm."""
    source = copy.deepcopy(source_root)
    prefix_ids(source, prefix + '-')
    group = etree.SubElement(parent, q('g'), transform=fit_transform(view_box(source), box, mode))
    if clip:
        clip_id = '%s-clip' % prefix
        clip_path = etree.SubElement(defs, q('clipPath'), id=clip_id)
        etree.SubElement(clip_path, q('rect'), x=_num(box[0]), y=_num(box[1]), width=_num(box[2]),
                         height=_num(box[3]))
        outer = etree.SubElement(parent, q('g'), {'clip-path': 'url(#%s)' % clip_id})
        outer.append(group)
    for child in source:
        if isinstance(child.tag, str) and etree.QName(child).localname in ('title', 'desc', 'metadata'):
            continue
        group.append(child)
    return group


class Outliner:
    """Glyph outlines of a font file (needs fontTools)."""

    def __init__(self, font_data):
        self.font = TTFont(io.BytesIO(font_data), lazy=True)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap() or {}
        self.upm = self.font['head'].unitsPerEm or 1000
        hhea = self.font['hhea']
        self.ascent, self.descent = hhea.ascent, hhea.descent
        self.hmtx = self.font['hmtx']

    def names(self, text):
        return [self.cmap.get(ord(char), '.notdef') for char in text]

    def advance(self, name):
        try:
            return self.hmtx[name][0]
        except KeyError:
            return 0

    def width(self, text, size):
        return sum(self.advance(name) for name in self.names(text)) * size / self.upm

    def baseline_offset(self, size):
        """Distance from the centre of a line to its baseline."""
        return (self.ascent + self.descent) / 2 / self.upm * size

    def path(self, text, x, baseline, size):
        """SVG path data of a line of text starting at (x, baseline), in mm."""
        scale = size / self.upm
        commands = []
        cursor = 0
        for name in self.names(text):
            if name in self.glyphs:
                pen = SVGPathPen(self.glyphs, ntos=lambda v: _num(v, 3))
                self.glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + cursor * scale, baseline)))
                if pen.getCommands():
                    commands.append(pen.getCommands())
            cursor += self.advance(name)
        return ' '.join(commands)


def outliner_for(font_data):
    if not font_data or TTFont is None:
        return None
    try:
        return Outliner(font_data)
    except Exception:  # noqa: BLE001 - a broken font falls back to <text>
        return None


def text_lines(element):
    text = element.get('text') or ''
    lines = text.splitlines() if element.get('multiline') else [' '.join(text.splitlines())]
    return lines or ['']


def layout_text(element, measure):
    """Font size and (line, x, centre y, width) of each line, in mm.

    measure(line, size) gives a line's width. Text shrinks to fit its box when
    the element has auto_fit; it is centred vertically in the box.
    """
    x, y, w, h = element['x'], element['y'], element['w'], element['h']
    lines = text_lines(element)
    size = max(element.get('font_size') or 5.0, 0.1)
    widest = max((measure(line, size) for line in lines), default=0)
    if element.get('auto_fit', True):
        factor = min(1.0, w / widest if widest else 1.0, h / (len(lines) * LINE_HEIGHT * size))
        size *= factor
    line_height = LINE_HEIGHT * size
    top = y + (h - len(lines) * line_height) / 2
    placed = []
    for index, line in enumerate(lines):
        width = measure(line, size)
        align = element.get('align') or 'center'
        if align == 'left':
            start = x
        elif align == 'right':
            start = x + w - width
        else:
            start = x + (w - width) / 2
        placed.append((line, start, top + index * line_height + line_height / 2, width))
    return size, placed


def estimate_width(line, size):
    """Rough width of a line when the font can't be measured."""
    return len(line) * size * 0.55


def add_text(parent, element, operation):
    """Add a text element: outlines when possible, else <text>."""
    if not (element.get('text') or '').strip():
        return
    color = safe_color(element.get('color'))
    outline = outliner_for(element.get('font_data'))
    paint = {'fill': 'none', 'stroke': color, 'stroke-width': _num(STROKE_WIDTH_MM)}
    if outline:
        size, lines = layout_text(element, outline.width)
        group = etree.SubElement(parent, q('g'), paint)
        for line, start, centre, _width in lines:
            data = outline.path(line, start, centre + outline.baseline_offset(size), size)
            if data:
                etree.SubElement(group, q('path'), d=data)
        return
    size, lines = layout_text(element, estimate_width)
    anchor = {'left': 'start', 'right': 'end'}.get(element.get('align'), 'middle')
    x = {
        'start': element['x'],
        'end': element['x'] + element['w'],
    }.get(anchor, element['x'] + element['w'] / 2)
    text = etree.SubElement(parent, q('text'), {
        'font-family': element.get('font_family') or 'sans-serif',
        'font-size': _num(size, 3),
        'text-anchor': anchor,
        **paint,
    })
    for line, _start, centre, _width in lines:
        span = etree.SubElement(text, q('tspan'), x=_num(x), y=_num(centre + size * 0.35))
        span.text = line


def build_svg(spec):
    """The .svg file of a cutting or scoring job, as bytes.

    spec: {'operation', 'width', 'height' (mm), 'base': {'data', 'ext'} or None,
    'elements': [{'type': 'text'|'image', 'x', 'y', 'w', 'h' (mm), 'text',
    'font_data', 'font_family', 'font_size', 'align', 'auto_fit', 'multiline',
    'color', 'fit', 'image', 'image_ext'}]}
    """
    width, height = float(spec['width']), float(spec['height'])
    root = etree.Element(q('svg'), nsmap=NSMAP, attrib={
        'version': '1.1',
        'width': '%smm' % _num(width),
        'height': '%smm' % _num(height),
        'viewBox': '0 0 %s %s' % (_num(width), _num(height)),
    })
    defs = etree.SubElement(root, q('defs'))
    base = spec.get('base')
    if base and base.get('data'):
        group = etree.SubElement(root, q('g'), id='base')
        embed_svg(group, defs, parse_svg(base['data']), (0, 0, width, height), 'contain', 'base')
    for index, element in enumerate(spec.get('elements') or []):
        box = (element['x'], element['y'], element['w'], element['h'])
        if element['type'] == 'text':
            add_text(root, element, spec.get('operation'))
        elif element.get('image'):
            embed_svg(root, defs, parse_svg(element['image']), box, element.get('fit') or 'contain',
                      'el%d' % index, clip=element.get('fit') == 'cover')
    if not len(defs):
        root.remove(defs)
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)

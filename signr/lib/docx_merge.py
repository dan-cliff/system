# -*- coding: utf-8 -*-
"""Fill in the merge codes of a Word (.docx) template.

A template marks where a value goes in one of two ways:

- typed text: ``{{ employee_id.job_id.name }}``;
- a Word merge field (Insert > Quick Parts > Field > MergeField) whose
  field name is the code: ``MERGEFIELD employee_id.job_id.name``.

Merge fields are turned into typed codes first, so both are filled in the
same way. Word often splits typed text over several runs (spell check,
formatting, edits); codes are found in a paragraph's whole text and written
into the run they start in, which keeps that run's formatting.

A table row whose codes go through a one-to-many or many-to-many field
(e.g. ``order_line.product_id.name``) is repeated once per linked record.

The values come from a *resolver* (see ``signr.template``):

- ``value(code, prefix=None, scope=None)``: the text (or an ``Image``) for a
  code, or None to leave the code as it is. In a repeated row, ``prefix`` is
  the repeating part of the code and ``scope`` the row's record;
- ``loop_prefix(code)``: the repeating part of a code, or None;
- ``loop_scopes(prefix)``: the records to repeat a row for.
"""
import io
import re
import zipfile
from copy import deepcopy

from lxml import etree

NSMAP = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
IMAGE_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
EMU_PER_CM = 360000
EMU_PER_PX = 9525  # at 96 dpi

CODE_RE = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')
MERGEFIELD_RE = re.compile(r'^\s*MERGEFIELD\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)
# Picture markers left in the text until it is split into runs (private-use characters).
IMG_OPEN, IMG_CLOSE = '\ue000', '\ue001'
TOKEN_RE = re.compile('(\n|\ue000\\d+\ue001)')

# The parts of a .docx that hold text with codes.
PART_RE = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')


def q(tag):
    prefix, name = tag.split(':')
    return '{%s}%s' % (NSMAP[prefix], name)


W_P, W_R, W_T, W_TR = q('w:p'), q('w:r'), q('w:t'), q('w:tr')
W_RPR, W_BR = q('w:rPr'), q('w:br')


class Image:
    """A picture to put where a code is, at most ``max_width_cm`` wide."""

    def __init__(self, data, max_width_cm=5.0, max_height_cm=3.0):
        self.data = data
        self.max_width_cm = max_width_cm
        self.max_height_cm = max_height_cm


class DocxError(ValueError):
    pass


# ----------------------------------------------------------------------
# Reading the package
# ----------------------------------------------------------------------
def _open(docx_bytes):
    try:
        archive = zipfile.ZipFile(io.BytesIO(docx_bytes))
    except zipfile.BadZipFile as error:
        raise DocxError('This is not a Word (.docx) document.') from error
    if 'word/document.xml' not in archive.namelist():
        raise DocxError('This is not a Word (.docx) document.')
    return archive


def _parse(data):
    return etree.fromstring(data, parser=etree.XMLParser(huge_tree=True, resolve_entities=False))


def _text_parts(archive):
    return [name for name in archive.namelist() if PART_RE.match(name)]


# ----------------------------------------------------------------------
# Merge fields -> typed codes
# ----------------------------------------------------------------------
def _code_run(code, rpr):
    run = etree.Element(W_R)
    if rpr is not None:
        run.append(deepcopy(rpr))
    text = etree.SubElement(run, W_T)
    text.text = '{{ %s }}' % code
    text.set(XML_SPACE, 'preserve')
    return run


def _merge_field_code(instruction):
    match = MERGEFIELD_RE.match(instruction or '')
    if not match:
        return None
    return (match.group(1) or match.group(2) or '').strip() or None


def _normalise_fields(root):
    """Replace Word MERGEFIELDs by a run holding ``{{ code }}``."""
    for simple in list(root.iter(q('w:fldSimple'))):
        code = _merge_field_code(simple.get(q('w:instr')))
        if not code:
            continue
        first_run = simple.find(W_R)
        rpr = first_run.find(W_RPR) if first_run is not None else None
        simple.getparent().replace(simple, _code_run(code, rpr))

    for paragraph in list(root.iter(W_P)):
        runs = list(paragraph.iter(W_R))
        index = 0
        while index < len(runs):
            run = runs[index]
            char = run.find(q('w:fldChar'))
            if char is None or char.get(q('w:fldCharType')) != 'begin':
                index += 1
                continue
            depth, instruction, separated, result_rpr = 1, '', False, None
            group = [run]
            nxt = index + 1
            while nxt < len(runs) and depth:
                other = runs[nxt]
                group.append(other)
                other_char = other.find(q('w:fldChar'))
                if other_char is not None:
                    kind = other_char.get(q('w:fldCharType'))
                    if kind == 'begin':
                        depth += 1
                    elif kind == 'end':
                        depth -= 1
                    elif kind == 'separate' and depth == 1:
                        separated = True
                elif depth == 1 and not separated:
                    instruction += ''.join(t.text or '' for t in other.findall(q('w:instrText')))
                elif depth == 1 and separated and result_rpr is None:
                    result_rpr = other.find(W_RPR)
                nxt += 1
            code = _merge_field_code(instruction) if not depth else None
            if code:
                group[0].addprevious(_code_run(code, result_rpr if result_rpr is not None else run.find(W_RPR)))
                for member in group:
                    member.getparent().remove(member)
            index = nxt


# ----------------------------------------------------------------------
# Paragraph text
# ----------------------------------------------------------------------
def _own_texts(paragraph):
    """The w:t of a paragraph, leaving out those of paragraphs nested in it (text boxes)."""
    texts = []
    for text in paragraph.iter(W_T):
        if next(text.iterancestors(W_P), None) is paragraph:
            texts.append(text)
    return texts


def _paragraph_codes(paragraph):
    text = ''.join(t.text or '' for t in _own_texts(paragraph))
    return [match.group(1).strip() for match in CODE_RE.finditer(text)]


def _replace_in_paragraph(paragraph, value_for, images):
    texts = _own_texts(paragraph)
    if not texts:
        return
    full, starts = '', []
    for text in texts:
        starts.append(len(full))
        full += text.text or ''
    matches = list(CODE_RE.finditer(full))
    if not matches:
        return

    def locate(position):
        for index in range(len(texts) - 1, -1, -1):
            if starts[index] <= position:
                return index
        return 0

    touched = set()
    for match in reversed(matches):
        value = value_for(match.group(1).strip())
        if value is None:
            continue
        if isinstance(value, Image):
            images.append(value)
            value = '%s%d%s' % (IMG_OPEN, len(images) - 1, IMG_CLOSE)
        first, last = locate(match.start()), locate(match.end() - 1)
        start_text, end_text = texts[first], texts[last]
        start_offset = match.start() - starts[first]
        end_offset = match.end() - starts[last]
        if first == last:
            original = start_text.text or ''
            start_text.text = original[:start_offset] + value + original[end_offset:]
        else:
            start_text.text = (start_text.text or '')[:start_offset] + value
            for middle in texts[first + 1:last]:
                middle.text = ''
            end_text.text = (end_text.text or '')[end_offset:]
            touched.update(texts[first:last + 1])
        touched.add(start_text)
    for text in touched:
        text.set(XML_SPACE, 'preserve')


def _expand_tokens(root, add_image):
    """Turn line breaks and picture markers left in w:t into w:br / w:drawing."""
    for text in list(root.iter(W_T)):
        value = text.text or ''
        if '\n' not in value and IMG_OPEN not in value:
            continue
        pieces = TOKEN_RE.split(value)
        text.text = pieces[0]
        anchor = text
        for piece in pieces[1:]:
            if not piece:
                continue
            if piece == '\n':
                element = etree.Element(W_BR)
            elif piece.startswith(IMG_OPEN):
                element = add_image(int(piece[1:-1]))
            else:
                element = etree.Element(W_T)
                element.text = piece
                element.set(XML_SPACE, 'preserve')
            if element is None:
                continue
            anchor.addnext(element)
            anchor = element


# ----------------------------------------------------------------------
# Pictures
# ----------------------------------------------------------------------
DRAWING = '''<w:drawing xmlns:w="{w}" xmlns:wp="{wp}" xmlns:a="{a}" xmlns:pic="{pic}" xmlns:r="{r}">
<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>
<wp:docPr id="{id}" name="Signr {id}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{id}" name="signr_{id}.png"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>
</wp:inline></w:drawing>'''


def _png_and_size(image):
    """The picture as PNG and its size in EMU, scaled to fit its maximum size."""
    from PIL import Image as PILImage
    with PILImage.open(io.BytesIO(image.data)) as picture:
        picture.load()
        width, height = picture.size
        output = io.BytesIO()
        picture.save(output, format='PNG')
    cx, cy = width * EMU_PER_PX, height * EMU_PER_PX
    ratio = min(1.0, image.max_width_cm * EMU_PER_CM / cx, image.max_height_cm * EMU_PER_CM / cy)
    return output.getvalue(), int(cx * ratio), int(cy * ratio)


def _rels_name(part):
    folder, _sep, name = part.rpartition('/')
    return f'{folder}/_rels/{name}.rels'


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def find_codes(docx_bytes):
    """The codes a template uses, in the order they first appear."""
    archive = _open(docx_bytes)
    codes = []
    for part in _text_parts(archive):
        root = _parse(archive.read(part))
        _normalise_fields(root)
        for paragraph in root.iter(W_P):
            for code in _paragraph_codes(paragraph):
                if code and code not in codes:
                    codes.append(code)
    return codes


def _attached(element, root):
    for ancestor in element.iterancestors():
        if ancestor is root:
            return True
    return element is root


def merge(docx_bytes, resolver):
    """The template with every code the resolver knows filled in, as .docx bytes."""
    archive = _open(docx_bytes)
    names = archive.namelist()
    files = {name: archive.read(name) for name in names}
    media = {}           # new file name -> bytes
    rels_roots = {}      # rels file -> parsed root
    counter = [0]

    def rels_for(part):
        rels_name = _rels_name(part)
        if rels_name not in rels_roots:
            if rels_name in files:
                rels_roots[rels_name] = _parse(files[rels_name])
            else:
                rels_roots[rels_name] = etree.Element(q('rel:Relationships'), nsmap={None: NSMAP['rel']})
        return rels_roots[rels_name]

    for part in _text_parts(archive):
        root = _parse(files[part])
        _normalise_fields(root)
        images = []

        for row in list(root.iter(W_TR)):
            if not _attached(row, root):
                continue
            codes = [code for paragraph in row.iter(W_P) for code in _paragraph_codes(paragraph)]
            prefix = next((p for p in (resolver.loop_prefix(code) for code in codes) if p), None)
            if not prefix:
                continue
            for scope in resolver.loop_scopes(prefix):
                clone = deepcopy(row)
                row.addprevious(clone)
                for paragraph in list(clone.iter(W_P)):
                    _replace_in_paragraph(
                        paragraph, lambda code, s=scope: resolver.value(code, prefix, s), images)
            row.getparent().remove(row)

        for paragraph in list(root.iter(W_P)):
            _replace_in_paragraph(paragraph, resolver.value, images)

        def add_image(index, part=part, images=images):
            try:
                png, cx, cy = _png_and_size(images[index])
            except Exception:  # noqa: BLE001 - an unreadable picture is left out
                return None
            counter[0] += 1
            number = counter[0]
            file_name = f'media/signr_{number}.png'
            media[f'word/{file_name}'] = png
            rels = rels_for(part)
            rid = f'rIdSignr{number}'
            etree.SubElement(rels, q('rel:Relationship'), Id=rid, Type=IMAGE_REL,
                             Target=file_name if part.count('/') == 1 else f'../{file_name}')
            return etree.fromstring(DRAWING.format(id=90000 + number, rid=rid, cx=cx, cy=cy, **NSMAP))

        _expand_tokens(root, add_image)
        files[part] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

    for rels_name, rels_root in rels_roots.items():
        files[rels_name] = etree.tostring(rels_root, xml_declaration=True, encoding='UTF-8', standalone=True)
    if media:
        types = _parse(files['[Content_Types].xml'])
        if not any((d.get('Extension') or '').lower() == 'png' for d in types.iter(q('ct:Default'))):
            types.insert(0, etree.Element(q('ct:Default'), Extension='png', ContentType='image/png'))
        files['[Content_Types].xml'] = etree.tostring(types, xml_declaration=True, encoding='UTF-8',
                                                      standalone=True)
        files.update(media)

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as result:
        # [Content_Types].xml first, as Word expects
        order = ['[Content_Types].xml'] + [n for n in files if n != '[Content_Types].xml']
        for name in order:
            result.writestr(name, files[name])
    return output.getvalue()

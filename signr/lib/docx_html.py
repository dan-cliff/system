# -*- coding: utf-8 -*-
"""Turn a .docx into PDF.

LibreOffice gives the closest copy of the Word layout, so it is used when the
server has it. Without it, the document is converted to simple HTML here
(paragraph and heading styles, bold / italic / underline, font sizes and
colours, alignment, indents, numbered and bulleted lists, tables, pictures
and page breaks) and printed with wkhtmltopdf by the caller. Headers and
footers are left out of the HTML version.
"""
import base64
import html
import logging
import os
import shutil
import subprocess
import tempfile

from .docx_merge import NSMAP, _open, _parse, q

_logger = logging.getLogger(__name__)

TWIP_PT = 1 / 20.0
EMU_PX = 1 / 9525.0
CONVERT_TIMEOUT = 180


# ----------------------------------------------------------------------
# LibreOffice
# ----------------------------------------------------------------------
def libreoffice_path():
    return shutil.which('soffice') or shutil.which('libreoffice')


def libreoffice_to_pdf(docx_bytes):
    """The document printed by LibreOffice, or None when it can't be."""
    binary = libreoffice_path()
    if not binary:
        return None
    with tempfile.TemporaryDirectory(prefix='signr_') as folder:
        source = os.path.join(folder, 'document.docx')
        with open(source, 'wb') as handle:
            handle.write(docx_bytes)
        profile = 'file://' + os.path.join(folder, 'profile')
        try:
            subprocess.run(
                [binary, f'-env:UserInstallation={profile}', '--headless', '--norestore',
                 '--convert-to', 'pdf', '--outdir', folder, source],
                check=True, capture_output=True, timeout=CONVERT_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            _logger.warning('Sign\'r: LibreOffice could not convert the document', exc_info=True)
            return None
        target = os.path.join(folder, 'document.pdf')
        if not os.path.exists(target):
            return None
        with open(target, 'rb') as handle:
            return handle.read()


# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------
def _val(element, tag, attr='w:val'):
    if element is None:
        return None
    child = element.find(q(tag))
    if child is None:
        return None
    return child.get(q(attr))


def _on(element, tag):
    if element is None:
        return False
    child = element.find(q(tag))
    if child is None:
        return False
    return child.get(q('w:val')) not in ('0', 'false', 'none')


class _Converter:

    def __init__(self, docx_bytes):
        self.archive = _open(docx_bytes)
        names = self.archive.namelist()
        self.document = _parse(self.archive.read('word/document.xml'))
        self.styles = {}
        if 'word/styles.xml' in names:
            for style in _parse(self.archive.read('word/styles.xml')).iter(q('w:style')):
                name = _val(style, 'w:name') or ''
                self.styles[style.get(q('w:styleId'))] = {
                    'name': name.lower(),
                    'rpr': style.find(q('w:rPr')),
                    'ppr': style.find(q('w:pPr')),
                }
        self.rels = {}
        if 'word/_rels/document.xml.rels' in names:
            for rel in _parse(self.archive.read('word/_rels/document.xml.rels')).iter(q('rel:Relationship')):
                self.rels[rel.get('Id')] = rel.get('Target')
        self.formats = {}  # (numId, ilvl) -> numFmt
        if 'word/numbering.xml' in names:
            numbering = _parse(self.archive.read('word/numbering.xml'))
            abstract = {}
            for node in numbering.iter(q('w:abstractNum')):
                abstract[node.get(q('w:abstractNumId'))] = {
                    lvl.get(q('w:ilvl')): _val(lvl, 'w:numFmt') or 'decimal' for lvl in node.iter(q('w:lvl'))}
            for num in numbering.iter(q('w:num')):
                levels = abstract.get(_val(num, 'w:abstractNumId'), {})
                for ilvl, fmt in levels.items():
                    self.formats[(num.get(q('w:numId')), ilvl)] = fmt
        self.counters = {}

    # -- runs ------------------------------------------------------------
    def _run_style(self, rpr, style_rpr=None):
        css = []
        for source in (style_rpr, rpr):
            if source is None:
                continue
            if _on(source, 'w:b'):
                css.append('font-weight:bold')
            if _on(source, 'w:i'):
                css.append('font-style:italic')
            underline = _val(source, 'w:u')
            if underline and underline != 'none':
                css.append('text-decoration:underline')
            if _on(source, 'w:strike'):
                css.append('text-decoration:line-through')
            if _on(source, 'w:caps'):
                css.append('text-transform:uppercase')
            size = _val(source, 'w:sz')
            if size and size.isdigit():
                css.append('font-size:%.1fpt' % (int(size) / 2.0))
            color = _val(source, 'w:color')
            if color and color != 'auto':
                css.append('color:#%s' % color)
            highlight = _val(source, 'w:highlight')
            if highlight and highlight != 'none':
                css.append('background-color:%s' % highlight)
            shade = source.find(q('w:shd'))
            if shade is not None and shade.get(q('w:fill')) not in (None, 'auto'):
                css.append('background-color:#%s' % shade.get(q('w:fill')))
            fonts = source.find(q('w:rFonts'))
            if fonts is not None and fonts.get(q('w:ascii')):
                css.append("font-family:'%s'" % fonts.get(q('w:ascii')).replace("'", ''))
        return ';'.join(css)

    def _image(self, drawing):
        blip = next(drawing.iter(q('a:blip')), None)
        if blip is None:
            return ''
        target = self.rels.get(blip.get(q('r:embed')))
        if not target:
            return ''
        path = target if target.startswith('word/') else 'word/' + target.lstrip('/')
        try:
            data = self.archive.read(path)
        except KeyError:
            return ''
        extension = path.rsplit('.', 1)[-1].lower()
        mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'gif': 'gif', 'bmp': 'bmp'}.get(extension, 'png')
        extent = next(drawing.iter(q('wp:extent')), None)
        size = ''
        if extent is not None:
            size = ' style="width:%dpx;height:%dpx"' % (
                int(int(extent.get('cx', 0)) * EMU_PX), int(int(extent.get('cy', 0)) * EMU_PX))
        return '<img src="data:image/%s;base64,%s"%s/>' % (mime, base64.b64encode(data).decode(), size)

    def _runs(self, paragraph, style_rpr):
        out = []
        for run in paragraph.iter(q('w:r')):
            if next(run.iterancestors(q('w:p')), None) is not paragraph:
                continue
            pieces = []
            for child in run:
                if child.tag == q('w:t'):
                    pieces.append(html.escape(child.text or ''))
                elif child.tag == q('w:tab'):
                    pieces.append('&emsp;')
                elif child.tag == q('w:br'):
                    if child.get(q('w:type')) == 'page':
                        pieces.append('<div class="signr-page-break"></div>')
                    else:
                        pieces.append('<br/>')
                elif child.tag == q('w:drawing'):
                    pieces.append(self._image(child))
            if not pieces:
                continue
            css = self._run_style(run.find(q('w:rPr')), style_rpr)
            text = ''.join(pieces)
            out.append('<span style="%s">%s</span>' % (css, text) if css else text)
        return ''.join(out)

    # -- paragraphs -------------------------------------------------------
    def _paragraph(self, paragraph):
        ppr = paragraph.find(q('w:pPr'))
        style = self.styles.get(_val(ppr, 'w:pStyle')) or {}
        name = style.get('name', '')
        tag = 'p'
        if name == 'title':
            tag = 'h1'
        elif name.startswith('heading '):
            level = name.split(' ', 1)[1]
            tag = 'h%s' % level if level in '123456' else 'h6'
        css = []
        for source in (style.get('ppr'), ppr):
            if source is None:
                continue
            align = _val(source, 'w:jc')
            if align:
                css.append('text-align:%s' % {'both': 'justify', 'start': 'left', 'end': 'right'}.get(align, align))
            spacing = source.find(q('w:spacing'))
            if spacing is not None:
                if spacing.get(q('w:before')):
                    css.append('margin-top:%.1fpt' % (int(spacing.get(q('w:before'))) * TWIP_PT))
                if spacing.get(q('w:after')):
                    css.append('margin-bottom:%.1fpt' % (int(spacing.get(q('w:after'))) * TWIP_PT))
            indent = source.find(q('w:ind'))
            if indent is not None:
                left = indent.get(q('w:left')) or indent.get(q('w:start'))
                if left and left.lstrip('-').isdigit():
                    css.append('margin-left:%.1fpt' % (int(left) * TWIP_PT))
            if _on(source, 'w:pageBreakBefore'):
                css.append('page-break-before:always')
        prefix = ''
        num = ppr.find(q('w:numPr')) if ppr is not None else None
        if num is not None:
            num_id, ilvl = _val(num, 'w:numId'), _val(num, 'w:ilvl') or '0'
            fmt = self.formats.get((num_id, ilvl), 'bullet')
            if num_id and num_id != '0':
                key = (num_id, ilvl)
                self.counters[key] = self.counters.get(key, 0) + 1
                # a new item at a level restarts the levels below it
                for other in list(self.counters):
                    if other[0] == num_id and other[1] > ilvl:
                        del self.counters[other]
                count = self.counters[key]
                if fmt == 'bullet':
                    prefix = '&bull;&ensp;'
                elif fmt in ('lowerLetter', 'upperLetter'):
                    letter = chr(ord('a') + (count - 1) % 26)
                    prefix = '%s)&ensp;' % (letter.upper() if fmt == 'upperLetter' else letter)
                elif fmt in ('lowerRoman', 'upperRoman'):
                    roman = _roman(count)
                    prefix = '%s.&ensp;' % (roman.upper() if fmt == 'upperRoman' else roman)
                else:
                    prefix = '%d.&ensp;' % count
                if not any(c.startswith('margin-left') for c in css):
                    css.append('margin-left:%dpt' % (18 * (int(ilvl) + 1)))
        content = self._runs(paragraph, style.get('rpr'))
        if not content and not prefix:
            content = '&nbsp;'
        return '<%s style="%s">%s%s</%s>' % (tag, ';'.join(css), prefix, content, tag)

    # -- tables -----------------------------------------------------------
    def _table(self, table):
        borders = table.find(q('w:tblPr') + '/' + q('w:tblBorders'))
        bordered = borders is not None and any(
            child.get(q('w:val')) not in (None, 'nil', 'none') for child in borders)
        rows = []
        for row in table.findall(q('w:tr')):
            cells = []
            for cell in row.findall(q('w:tc')):
                tcpr = cell.find(q('w:tcPr'))
                attrs, css = '', []
                span = _val(tcpr, 'w:gridSpan')
                if span and span.isdigit() and int(span) > 1:
                    attrs += ' colspan="%s"' % span
                width = tcpr.find(q('w:tcW')) if tcpr is not None else None
                if width is not None and width.get(q('w:type')) == 'dxa' and width.get(q('w:w'), '').isdigit():
                    css.append('width:%.1fpt' % (int(width.get(q('w:w'))) * TWIP_PT))
                shade = tcpr.find(q('w:shd')) if tcpr is not None else None
                if shade is not None and shade.get(q('w:fill')) not in (None, 'auto'):
                    css.append('background-color:#%s' % shade.get(q('w:fill')))
                merge = tcpr.find(q('w:vMerge')) if tcpr is not None else None
                if merge is not None and merge.get(q('w:val')) != 'restart':
                    css.append('border-top:none')
                    content = ''
                else:
                    content = self._blocks(cell)
                cells.append('<td%s style="%s">%s</td>' % (attrs, ';'.join(css), content))
            rows.append('<tr>%s</tr>' % ''.join(cells))
        return '<table class="%s">%s</table>' % ('signr-bordered' if bordered else '', ''.join(rows))

    def _blocks(self, container):
        out = []
        for child in container:
            if child.tag == q('w:p'):
                out.append(self._paragraph(child))
            elif child.tag == q('w:tbl'):
                out.append(self._table(child))
            elif child.tag == q('w:sdt'):
                content = child.find(q('w:sdtContent'))
                if content is not None:
                    out.append(self._blocks(content))
        return ''.join(out)

    def convert(self):
        body = self.document.find(q('w:body'))
        return self._blocks(body) if body is not None else ''


def _roman(number):
    values = [(1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'),
              (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')]
    result = ''
    for value, letters in values:
        while number >= value:
            result += letters
            number -= value
    return result


# wkhtmltopdf prints CSS points smaller than Word does: zoom brings them back to size.
STYLE = '''
body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000; zoom: 1.35; margin: 0 12mm; }
p { margin: 0 0 6pt 0; line-height: 1.2; }
h1, h2, h3, h4, h5, h6 { margin: 12pt 0 6pt 0; }
table { border-collapse: collapse; width: 100%; margin-bottom: 6pt; }
td { vertical-align: top; padding: 2pt 4pt; }
table.signr-bordered td { border: 1px solid #000; }
td p { margin-bottom: 0; }
.signr-page-break { page-break-after: always; }
img { max-width: 100%; }
'''


def to_html(docx_bytes):
    """The document as a standalone HTML page."""
    body = _Converter(docx_bytes).convert()
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"/><style>%s</style></head>'
            '<body>%s</body></html>' % (STYLE, body))


__all__ = ['libreoffice_path', 'libreoffice_to_pdf', 'to_html', 'NSMAP']

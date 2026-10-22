"""Convert a PowerPoint (.pptx) or Google Slides export into authoring slides.

Pure Python (zipfile + lxml) so it runs on any Odoo host without extra
libraries. ``PptxConverter(data).convert()`` returns::

    {
        'width': 1280, 'height': 720,
        'slides': [{'name', 'notes', 'background_color', 'background_media',
                    'elements': [...]}],
        'media': {key: {'name', 'data', 'mimetype'}},
        'warnings': [str],
    }

Elements use the same structure as the editor and the player (see
``static/player/player.js``); pictures reference ``props.media`` keys which
the caller swaps for stored attachments.
"""
import colorsys
import html
import io
import mimetypes
import posixpath
import re
import uuid
import zipfile

from lxml import etree

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'p14': 'http://schemas.microsoft.com/office/powerpoint/2010/main',
}
R_EMBED = '{%s}embed' % NS['r']
R_LINK = '{%s}link' % NS['r']
R_ID = '{%s}id' % NS['r']

EMU_PER_PX = 9525  # 914400 EMU per inch / 96 px per inch
MAX_FILE_SIZE = 200 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_SLIDES = 500
WEB_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/svg+xml', 'image/webp', 'image/bmp'}
WEB_VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/ogg'}
WEB_AUDIO_TYPES = {'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/webm'}
PRESENTATION_TYPES = (
    'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
    'application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml',
    'application/vnd.openxmlformats-officedocument.presentationml.template.main+xml',
    'application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml',
    'application/vnd.ms-powerpoint.slideshow.macroEnabled.main+xml',
)
TITLE_TYPES = ('title', 'ctrTitle')
SKIP_PLACEHOLDERS = ('dt', 'ftr', 'sldNum', 'hdr')
DEFAULT_SIZES_PT = {'title': 40, 'ctrTitle': 44, 'subTitle': 24, 'body': 20, 'other': 18}


class PresentationError(Exception):
    """A problem with the uploaded file, worded for the user."""


def _new_id():
    return 'e' + uuid.uuid4().hex[:10]


def _xml_parser():
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False,
                           remove_blank_text=False)


class PptxConverter:

    def __init__(self, data, target_width=1280):
        self.data = data
        self.target_width = target_width
        self.zip = None
        self.warnings = []
        self.media = {}
        self._media_by_part = {}
        self._xml_cache = {}
        self.scale = 1.0
        self.theme_colors = {}
        self.theme_fonts = {}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self):
        """Check the file is a usable presentation; raise PresentationError if not."""
        data = self.data or b''
        if not data:
            raise PresentationError('The file is empty.')
        if len(data) > MAX_FILE_SIZE:
            raise PresentationError('The file is larger than %d MB.' % (MAX_FILE_SIZE // (1024 * 1024)))
        if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            raise PresentationError(
                'This looks like an old-style .ppt file or a password-protected presentation. '
                'Open it in PowerPoint, remove any password and save it as .pptx, then upload it again.')
        if data[:2] != b'PK':
            raise PresentationError(
                'This is not a PowerPoint (.pptx) file. In Google Slides use '
                'File > Download > Microsoft PowerPoint (.pptx), or give the share link instead.')
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise PresentationError('The file is damaged and could not be opened.')
        names = set(self.zip.namelist())
        total = sum(info.file_size for info in self.zip.infolist())
        if total > MAX_UNCOMPRESSED:
            raise PresentationError('The presentation is too large to convert once unpacked.')
        if '[Content_Types].xml' not in names or 'ppt/presentation.xml' not in names:
            raise PresentationError(
                'The file is not a PowerPoint presentation (it may be a Word or Excel document).')
        content_types = self._read('[Content_Types].xml')
        main_type = None
        for override in content_types.iter('{*}Override'):
            if override.get('PartName') == '/ppt/presentation.xml':
                main_type = override.get('ContentType')
        if main_type and main_type not in PRESENTATION_TYPES:
            raise PresentationError('Unsupported presentation type: %s' % main_type)
        if main_type and 'macroEnabled' in main_type:
            self.warnings.append('The presentation contains macros; they were ignored.')
        slide_ids = self._slide_parts()
        if not slide_ids:
            raise PresentationError('The presentation has no slides.')
        if len(slide_ids) > MAX_SLIDES:
            raise PresentationError('The presentation has more than %d slides.' % MAX_SLIDES)
        return True

    # ------------------------------------------------------------------
    # Package helpers
    # ------------------------------------------------------------------
    def _read(self, part):
        if part not in self._xml_cache:
            try:
                raw = self.zip.read(part)
            except KeyError:
                self._xml_cache[part] = None
            else:
                try:
                    self._xml_cache[part] = etree.fromstring(raw, parser=_xml_parser())
                except etree.XMLSyntaxError:
                    self._xml_cache[part] = None
        return self._xml_cache[part]

    def _rels(self, part):
        """Return {rId: (target_part_or_url, type, external)} for a part."""
        folder, name = posixpath.split(part)
        rels_xml = self._read(posixpath.join(folder, '_rels', name + '.rels'))
        result = {}
        if rels_xml is None:
            return result
        for rel in rels_xml.iter('{%s}Relationship' % NS['rel']):
            target = rel.get('Target') or ''
            external = rel.get('TargetMode') == 'External'
            if not external:
                if target.startswith('/'):
                    target = target.lstrip('/')
                else:
                    target = posixpath.normpath(posixpath.join(folder, target))
            result[rel.get('Id')] = (target, rel.get('Type', '').rsplit('/', 1)[-1], external)
        return result

    def _rel_of_type(self, part, rel_type):
        for target, typ, external in self._rels(part).values():
            if typ == rel_type and not external:
                return target
        return None

    def _slide_parts(self):
        pres = self._read('ppt/presentation.xml')
        if pres is None:
            return []
        rels = self._rels('ppt/presentation.xml')
        parts = []
        for sld in pres.findall('p:sldIdLst/p:sldId', NS):
            rel = rels.get(sld.get(R_ID))
            if rel and not rel[2]:
                parts.append(rel[0])
        return parts

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _load_theme(self, master_part):
        theme_part = self._rel_of_type(master_part, 'theme')
        theme = self._read(theme_part) if theme_part else None
        colors, fonts = {}, {}
        if theme is not None:
            scheme = theme.find('.//a:clrScheme', NS)
            if scheme is not None:
                for child in scheme:
                    name = etree.QName(child).localname
                    srgb = child.find('a:srgbClr', NS)
                    sys_clr = child.find('a:sysClr', NS)
                    if srgb is not None:
                        colors[name] = srgb.get('val')
                    elif sys_clr is not None:
                        colors[name] = sys_clr.get('lastClr') or '000000'
            major = theme.find('.//a:fontScheme/a:majorFont/a:latin', NS)
            minor = theme.find('.//a:fontScheme/a:minorFont/a:latin', NS)
            if major is not None:
                fonts['+mj-lt'] = major.get('typeface')
            if minor is not None:
                fonts['+mn-lt'] = minor.get('typeface')
        master = self._read(master_part)
        clr_map = master.find('p:clrMap', NS) if master is not None else None
        mapping = dict(clr_map.attrib) if clr_map is not None else {
            'bg1': 'lt1', 'tx1': 'dk1', 'bg2': 'lt2', 'tx2': 'dk2'}
        for alias, target in mapping.items():
            if target in colors:
                colors[alias] = colors[target]
        return colors, fonts

    # ------------------------------------------------------------------
    # Colours
    # ------------------------------------------------------------------
    def _color(self, fill_parent):
        """Resolve the colour of an element holding a*Clr children (e.g. a:solidFill)."""
        if fill_parent is None:
            return None
        for node in fill_parent:
            if not isinstance(node.tag, str):
                continue
            tag = etree.QName(node).localname
            hex_value = None
            if tag == 'srgbClr':
                hex_value = node.get('val')
            elif tag == 'schemeClr':
                hex_value = self.theme_colors.get(node.get('val'))
            elif tag == 'sysClr':
                hex_value = node.get('lastClr')
            elif tag == 'prstClr':
                hex_value = {'black': '000000', 'white': 'FFFFFF', 'red': 'FF0000',
                             'green': '008000', 'blue': '0000FF', 'yellow': 'FFFF00',
                             'gray': '808080', 'grey': '808080'}.get(node.get('val'))
            elif tag == 'scrgbClr':
                try:
                    hex_value = ''.join('%02X' % round(int(node.get(c)) / 100000 * 255)
                                        for c in ('r', 'g', 'b'))
                except (TypeError, ValueError):
                    hex_value = None
            if not hex_value:
                continue
            return self._apply_mods(hex_value, node)
        return None

    def _apply_mods(self, hex_value, node):
        try:
            r, g, b = (int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4))
        except ValueError:
            return None
        alpha = 1.0
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        for mod in node:
            if not isinstance(mod.tag, str):
                continue
            name = etree.QName(mod).localname
            try:
                val = int(mod.get('val')) / 100000
            except (TypeError, ValueError):
                continue
            if name == 'lumMod':
                l *= val
            elif name == 'lumOff':
                l += val
            elif name == 'tint':
                l = l + (1 - l) * (1 - val)
            elif name == 'shade':
                l *= val
            elif name == 'alpha':
                alpha = val
        l = min(max(l, 0), 1)
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        if alpha < 0.999:
            return 'rgba(%d, %d, %d, %.2f)' % (round(r * 255), round(g * 255), round(b * 255), alpha)
        return '#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))

    def _fill(self, sp_pr):
        """Return (css colour or None, media key or None) for a spPr / bgPr."""
        if sp_pr is None:
            return None, None
        if sp_pr.find('a:noFill', NS) is not None:
            return None, None
        solid = sp_pr.find('a:solidFill', NS)
        if solid is not None:
            return self._color(solid), None
        grad = sp_pr.find('a:gradFill', NS)
        if grad is not None:
            stops = []
            for gs in grad.findall('a:gsLst/a:gs', NS):
                color = self._color(gs)
                if color:
                    stops.append('%s %d%%' % (color, int(gs.get('pos', '0')) // 1000))
            if len(stops) >= 2:
                lin = grad.find('a:lin', NS)
                angle = int(lin.get('ang', '0')) / 60000 + 90 if lin is not None else 180
                return 'linear-gradient(%ddeg, %s)' % (angle, ', '.join(stops)), None
            if stops:
                return stops[0].rsplit(' ', 1)[0], None
        return None, None

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------
    def _media(self, part, allowed, kind):
        """Register a media part and return its key, or None when unusable."""
        if part in self._media_by_part:
            return self._media_by_part[part]
        try:
            data = self.zip.read(part)
        except KeyError:
            return None
        name = posixpath.basename(part)
        mimetype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        if name.lower().endswith('.m4a'):
            mimetype = 'audio/mp4'
        if mimetype not in allowed:
            self.warnings.append(
                'A %s in %s format could not be used in a web course and was skipped.'
                % (kind, name.rsplit('.', 1)[-1].upper()))
            self._media_by_part[part] = None
            return None
        key = 'm%d' % (len(self.media) + 1)
        self.media[key] = {'name': name, 'data': data, 'mimetype': mimetype}
        self._media_by_part[part] = key
        return key

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    @staticmethod
    def _xfrm(node):
        xfrm = node.find('p:spPr/a:xfrm', NS)
        if xfrm is None:
            xfrm = node.find('p:xfrm', NS)
        if xfrm is None:
            xfrm = node.find('p:grpSpPr/a:xfrm', NS)
        return xfrm

    @staticmethod
    def _box(xfrm):
        if xfrm is None:
            return None
        off = xfrm.find('a:off', NS)
        ext = xfrm.find('a:ext', NS)
        if off is None or ext is None:
            return None
        try:
            return {
                'x': int(off.get('x')), 'y': int(off.get('y')),
                'w': int(ext.get('cx')), 'h': int(ext.get('cy')),
                'rot': int(xfrm.get('rot', '0')) / 60000,
            }
        except (TypeError, ValueError):
            return None

    def _to_px(self, box, transform):
        x, y, w, h = transform(box['x'], box['y'], box['w'], box['h'])
        s = self.scale / EMU_PER_PX
        return {
            'x': round(x * s), 'y': round(y * s),
            'w': max(round(w * s), 4), 'h': max(round(h * s), 4),
            'rotation': round(box.get('rot', 0)) % 360,
        }

    # ------------------------------------------------------------------
    # Placeholders and text styles
    # ------------------------------------------------------------------
    @staticmethod
    def _placeholder(node):
        ph = node.find('p:nvSpPr/p:nvPr/p:ph', NS)
        if ph is None:
            ph = node.find('p:nvPicPr/p:nvPr/p:ph', NS)
        if ph is None:
            ph = node.find('p:nvGraphicFramePr/p:nvPr/p:ph', NS)
        if ph is None:
            return None
        return {'type': ph.get('type', 'obj'), 'idx': ph.get('idx')}

    def _find_placeholder(self, tree, ph, master=False):
        if tree is None or not ph:
            return None
        candidates = []
        for sp in tree.iterfind('.//p:cSld/p:spTree/*', NS):
            other = self._placeholder(sp)
            if other:
                candidates.append((sp, other))
        if not master and ph.get('idx'):
            for sp, other in candidates:
                if other.get('idx') == ph['idx']:
                    return sp
        wanted = ph['type']
        if master:
            wanted = 'title' if wanted in TITLE_TYPES else (
                wanted if wanted in SKIP_PLACEHOLDERS else 'body')
        for sp, other in candidates:
            typ = other['type']
            if typ == wanted or (wanted in TITLE_TYPES and typ in TITLE_TYPES):
                return sp
        return None

    def _style_sources(self, ctx, node, ph):
        """List of lstStyle-like nodes to look up paragraph/run defaults, highest priority first."""
        sources = []
        if ph:
            layout_sp = self._find_placeholder(ctx['layout'], ph)
            master_sp = self._find_placeholder(ctx['master'], ph, master=True)
            for sp in (layout_sp, master_sp):
                if sp is not None:
                    sources.append(sp.find('p:txBody/a:lstStyle', NS))
            master = ctx['master']
            if master is not None:
                if ph['type'] in TITLE_TYPES:
                    sources.append(master.find('p:txStyles/p:titleStyle', NS))
                elif ph['type'] not in SKIP_PLACEHOLDERS:
                    sources.append(master.find('p:txStyles/p:bodyStyle', NS))
                else:
                    sources.append(master.find('p:txStyles/p:otherStyle', NS))
        else:
            master = ctx['master']
            if master is not None:
                sources.append(master.find('p:txStyles/p:otherStyle', NS))
        pres = self._read('ppt/presentation.xml')
        if pres is not None:
            sources.append(pres.find('p:defaultTextStyle', NS))
        return [s for s in sources if s is not None]

    @staticmethod
    def _lvl(sources, level, tag):
        """First node ``a:lvl{n}pPr/<tag>`` found in sources (tag '' returns the pPr)."""
        for src in sources:
            ppr = src.find('a:lvl%dpPr' % (level + 1), NS)
            if ppr is None:
                continue
            if not tag:
                return ppr
            found = ppr.find(tag, NS)
            if found is not None:
                return found
        return None

    def _run_style(self, rpr_list, font_ref_color, inherited=()):
        """Merge run properties (highest priority first) into a dict of CSS values.

        The shape's own font colour (``p:style/a:fontRef``) beats the inherited
        master text styles but not the run or the shape's own list style.
        """
        style = {}
        for index, rpr in enumerate(list(rpr_list) + [None] + list(inherited)):
            if index == len(rpr_list):
                if 'color' not in style and font_ref_color:
                    style['color'] = font_ref_color
                continue
            if rpr is None:
                continue
            if 'size' not in style and rpr.get('sz'):
                try:
                    style['size'] = int(rpr.get('sz')) / 100
                except ValueError:
                    pass
            for attr in ('b', 'i'):
                if attr not in style and rpr.get(attr) is not None:
                    style[attr] = rpr.get(attr) in ('1', 'true')
            if 'u' not in style and rpr.get('u') is not None:
                style['u'] = rpr.get('u') != 'none'
            if 'strike' not in style and rpr.get('strike') is not None:
                style['strike'] = rpr.get('strike') != 'noStrike'
            if 'color' not in style:
                fill = rpr.find('a:solidFill', NS)
                if fill is not None:
                    color = self._color(fill)
                    if color:
                        style['color'] = color
            if 'font' not in style:
                latin = rpr.find('a:latin', NS)
                if latin is not None and latin.get('typeface'):
                    face = latin.get('typeface')
                    face = self.theme_fonts.get(face, face)
                    if face and not face.startswith('+'):
                        style['font'] = face
        return style

    def _css_for_run(self, style, base):
        css = []
        size = style.get('size')
        if size and size != base.get('size'):
            css.append('font-size:%dpx' % round(size * 96 / 72 * self.scale))
        if style.get('color') and style.get('color') != base.get('color'):
            css.append('color:%s' % style['color'])
        if style.get('font') and style.get('font') != base.get('font'):
            css.append("font-family:'%s', sans-serif" % style['font'].replace("'", ''))
        decoration = []
        if style.get('u'):
            decoration.append('underline')
        if style.get('strike'):
            decoration.append('line-through')
        if decoration:
            css.append('text-decoration:%s' % ' '.join(decoration))
        return ';'.join(css)

    def _text_html(self, ctx, node, tx_body, ph, rels):
        """Convert a txBody into (html, base style dict, plain text)."""
        own_style = tx_body.find('a:lstStyle', NS)
        inherited = self._style_sources(ctx, node, ph) if node is not None else []
        font_ref = node.find('p:style/a:fontRef', NS) if node is not None else None
        font_ref_color = self._color(font_ref) if font_ref is not None else None
        paragraphs = tx_body.findall('a:p', NS)
        default_type = 'other'
        if ph:
            default_type = ph['type'] if ph['type'] in DEFAULT_SIZES_PT else (
                'title' if ph['type'] in TITLE_TYPES else 'body')

        # The base (element-level) style comes from the first paragraph with text.
        base = {}
        plain = []
        out = []
        list_stack = None  # 'ul' / 'ol' currently open
        for para in paragraphs:
            ppr = para.find('a:pPr', NS)
            level = int(ppr.get('lvl', '0')) if ppr is not None and ppr.get('lvl', '0').isdigit() else 0
            own = [own_style] if own_style is not None else []
            lvl_ppr = self._lvl(own + inherited, level, '')
            own_rpr = self._lvl(own, level, 'a:defRPr')
            inherited_rpr = self._lvl(inherited, level, 'a:defRPr')
            algn = (ppr.get('algn') if ppr is not None else None) or (
                lvl_ppr.get('algn') if lvl_ppr is not None else None)

            # Bullets: explicit on the paragraph, else inherited from the level style
            bullet = None
            for src in ([ppr] if ppr is not None else []) + ([lvl_ppr] if lvl_ppr is not None else []):
                if src.find('a:buNone', NS) is not None:
                    bullet = 'none'
                    break
                if src.find('a:buAutoNum', NS) is not None:
                    bullet = 'ol'
                    break
                if src.find('a:buChar', NS) is not None:
                    bullet = 'ul'
                    break
            if bullet == 'none':
                bullet = None

            runs_html = []
            para_text = []
            first_style = None
            for child in para:
                if not isinstance(child.tag, str):
                    continue
                tag = etree.QName(child).localname
                if tag == 'br':
                    runs_html.append('<br/>')
                    para_text.append('\n')
                    continue
                if tag not in ('r', 'fld'):
                    continue
                text = ''.join(child.findtext('a:t', '', NS) or '')
                if not text:
                    continue
                rpr = child.find('a:rPr', NS)
                style = self._run_style([rpr, own_rpr], font_ref_color, [inherited_rpr])
                if 'size' not in style:
                    style['size'] = DEFAULT_SIZES_PT.get(default_type, 18)
                if first_style is None:
                    first_style = style
                if not base:
                    base = dict(style)
                piece = html.escape(text).replace('\t', '&#9;')
                css = self._css_for_run(style, base)
                if style.get('b') and not base.get('b'):
                    piece = '<strong>%s</strong>' % piece
                elif base.get('b') and style.get('b') is False:
                    piece = '<span style="font-weight:normal">%s</span>' % piece
                if style.get('i') and not base.get('i'):
                    piece = '<em>%s</em>' % piece
                if css:
                    piece = '<span style="%s">%s</span>' % (css, piece)
                link = rpr.find('a:hlinkClick', NS) if rpr is not None else None
                if link is not None and link.get(R_ID) in rels and rels[link.get(R_ID)][2]:
                    href = rels[link.get(R_ID)][0]
                    if href.lower().startswith(('http://', 'https://', 'mailto:')):
                        piece = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (
                            html.escape(href, quote=True), piece)
                runs_html.append(piece)
                para_text.append(text)

            text_line = ''.join(para_text)
            plain.append(text_line)
            align_css = {'ctr': 'center', 'r': 'right', 'just': 'justify'}.get(algn)
            p_style = ' style="text-align:%s"' % align_css if align_css else ''
            content = ''.join(runs_html) or '<br/>'
            if bullet and text_line.strip():
                if list_stack != bullet:
                    if list_stack:
                        out.append('</%s>' % list_stack)
                    out.append('<%s>' % bullet)
                    list_stack = bullet
                indent = ' style="margin-left:%dem%s"' % (
                    level * 1.5, ';text-align:%s' % align_css if align_css else '') if level else p_style
                out.append('<li%s>%s</li>' % (indent, content))
            else:
                if list_stack:
                    out.append('</%s>' % list_stack)
                    list_stack = None
                out.append('<p%s>%s</p>' % (p_style, content))
        if list_stack:
            out.append('</%s>' % list_stack)
        # Trim trailing empty paragraphs
        while out and out[-1] == '<p><br/></p>':
            out.pop()
        return ''.join(out), base, '\n'.join(plain).strip()

    # ------------------------------------------------------------------
    # Shapes
    # ------------------------------------------------------------------
    def _line_style(self, sp_pr, node):
        ln = sp_pr.find('a:ln', NS) if sp_pr is not None else None
        if ln is None:
            ref = node.find('p:style/a:lnRef', NS)
            if ref is not None and ref.get('idx', '0') != '0' and node.tag.endswith('cxnSp'):
                return self._color(ref) or '#000000', 1
            return None, 0
        if ln.find('a:noFill', NS) is not None:
            return None, 0
        color = self._color(ln.find('a:solidFill', NS))
        try:
            width = max(round(int(ln.get('w', '12700')) / EMU_PER_PX * self.scale), 1)
        except ValueError:
            width = 1
        return color, width if color else 0

    def _shape_fill(self, node, sp_pr):
        color, _media = self._fill(sp_pr)
        if color is None and (sp_pr is None or sp_pr.find('a:noFill', NS) is None):
            ref = node.find('p:style/a:fillRef', NS)
            if ref is not None and ref.get('idx', '0') != '0':
                color = self._color(ref)
        return color

    def _convert_sp(self, ctx, node, transform, rels, elements, from_layout):
        ph = self._placeholder(node)
        if ph and from_layout:
            return  # Layout/master placeholders are prompts, not content
        if ph and ph['type'] in SKIP_PLACEHOLDERS and not from_layout:
            tx = node.find('p:txBody', NS)
            if tx is None or not ''.join(tx.itertext()).strip():
                return
        box = self._box(self._xfrm(node))
        if box is None and ph:
            for tree, master in ((ctx['layout'], False), (ctx['master'], True)):
                sp = self._find_placeholder(tree, ph, master=master)
                if sp is not None:
                    box = self._box(self._xfrm(sp))
                    if box:
                        break
        if box is None:
            return
        geom = self._to_px(box, transform)
        sp_pr = node.find('p:spPr', NS)
        fill = self._shape_fill(node, sp_pr)
        line_color, line_width = self._line_style(sp_pr, node)
        prst = sp_pr.find('a:prstGeom', NS) if sp_pr is not None else None
        prst = prst.get('prst') if prst is not None else 'rect'
        shape = {'ellipse': 'ellipse', 'roundRect': 'roundRect', 'line': 'line',
                 'straightConnector1': 'line'}.get(prst, 'rect')
        if prst not in ('rect', 'ellipse', 'roundRect', 'line', 'straightConnector1') and (fill or line_color):
            ctx['custom_shapes'] += 1

        style = {}
        if fill:
            style['background'] = fill
        if line_color and line_width:
            style['borderColor'] = line_color
            style['borderWidth'] = line_width
        if shape == 'roundRect':
            style['radius'] = round(min(geom['w'], geom['h']) * 0.16)
        elif shape == 'ellipse':
            style['radius'] = 9999

        tx_body = node.find('p:txBody', NS)
        text_html, base, plain = ('', {}, '')
        if tx_body is not None:
            text_html, base, plain = self._text_html(ctx, node, tx_body, ph, rels)
        if plain:
            body_pr = tx_body.find('a:bodyPr', NS)
            anchor = body_pr.get('anchor') if body_pr is not None else None
            if anchor is None and ph and ph['type'] in ('ctrTitle',):
                anchor = 'ctr'
            if anchor is None and ph:
                for tree, master in ((ctx['layout'], False), (ctx['master'], True)):
                    sp = self._find_placeholder(tree, ph, master=master)
                    bp = sp.find('p:txBody/a:bodyPr', NS) if sp is not None else None
                    if bp is not None and bp.get('anchor'):
                        anchor = bp.get('anchor')
                        break
            style['fontSize'] = round(base.get('size', 18) * 96 / 72 * self.scale)
            if base.get('color'):
                style['color'] = base['color']
            if base.get('font'):
                style['fontFamily'] = "'%s', sans-serif" % base['font'].replace("'", '')
            if base.get('b'):
                style['bold'] = True
            if base.get('i'):
                style['italic'] = True
            if shape == 'ellipse' and fill:
                style['radius'] = 9999
            elements.append({
                'id': _new_id(), 'type': 'text', **geom, 'required': False,
                'props': {
                    'html': text_html,
                    'valign': {'ctr': 'middle', 'b': 'bottom'}.get(anchor, 'top'),
                    'role': 'title' if ph and ph['type'] in TITLE_TYPES else '',
                },
                'style': style,
            })
            if ph and ph['type'] in TITLE_TYPES and not ctx['title']:
                ctx['title'] = plain.replace('\n', ' ')[:120]
        elif fill or line_color:
            if shape == 'line':
                style = {'borderColor': line_color or '#000000', 'borderWidth': line_width or 1}
            elements.append({
                'id': _new_id(), 'type': 'shape', **geom, 'required': False,
                'props': {'shape': shape}, 'style': style,
            })

    def _convert_pic(self, ctx, node, transform, rels, elements):
        box = self._box(self._xfrm(node))
        ph = self._placeholder(node)
        if box is None and ph:
            sp = self._find_placeholder(ctx['layout'], ph)
            box = self._box(self._xfrm(sp)) if sp is not None else None
        if box is None:
            return
        geom = self._to_px(box, transform)
        nv_pr = node.find('p:nvPicPr/p:nvPr', NS)
        # Embedded video / audio
        if nv_pr is not None:
            media_el = None
            for path in ('a:videoFile', 'a:audioFile', 'p:extLst/p:ext/p14:media'):
                media_el = nv_pr.find(path, NS)
                if media_el is not None:
                    break
            if media_el is not None:
                rid = media_el.get(R_EMBED) or media_el.get(R_LINK)
                rel = rels.get(rid)
                is_audio = etree.QName(media_el).localname == 'audioFile'
                if rel and rel[2] and not is_audio:
                    elements.append({'id': _new_id(), 'type': 'video', **geom, 'required': False,
                                     'props': {'url': rel[0], 'media': ''}, 'style': {}})
                    return
                if rel and not rel[2]:
                    mimetype = mimetypes.guess_type(rel[0])[0] or ''
                    is_audio = is_audio or mimetype.startswith('audio/')
                    key = self._media(rel[0], WEB_AUDIO_TYPES if is_audio else WEB_VIDEO_TYPES,
                                      'audio clip' if is_audio else 'video')
                    if key:
                        elements.append({
                            'id': _new_id(), 'type': 'audio' if is_audio else 'video', **geom,
                            'required': False, 'props': {'media': key, 'url': ''}, 'style': {}})
                        return
        blip = node.find('p:blipFill/a:blip', NS)
        rid = blip.get(R_EMBED) if blip is not None else None
        rel = rels.get(rid)
        if not rel or rel[2]:
            return
        key = self._media(rel[0], WEB_IMAGE_TYPES, 'picture')
        if not key:
            return
        descr = node.find('p:nvPicPr/p:cNvPr', NS)
        elements.append({
            'id': _new_id(), 'type': 'image', **geom, 'required': False,
            'props': {'media': key, 'alt': (descr.get('descr') or '') if descr is not None else '',
                      'fit': 'fill'},
            'style': {},
        })

    def _convert_table(self, ctx, node, transform, rels, elements):
        box = self._box(self._xfrm(node))
        tbl = node.find('a:graphic/a:graphicData/a:tbl', NS)
        if box is None or tbl is None:
            return
        geom = self._to_px(box, transform)
        widths = []
        for col in tbl.findall('a:tblGrid/a:gridCol', NS):
            try:
                widths.append(int(col.get('w')))
            except (TypeError, ValueError):
                widths.append(0)
        total = sum(widths) or 1
        rows_html = []
        base_size = None
        for row in tbl.findall('a:tr', NS):
            cells = []
            for tc in row.findall('a:tc', NS):
                if tc.get('hMerge') == '1' or tc.get('vMerge') == '1':
                    continue
                attrs = []
                if tc.get('gridSpan'):
                    attrs.append('colspan="%s"' % html.escape(tc.get('gridSpan')))
                if tc.get('rowSpan'):
                    attrs.append('rowspan="%s"' % html.escape(tc.get('rowSpan')))
                tc_pr = tc.find('a:tcPr', NS)
                bg, _m = self._fill(tc_pr)
                css = 'border:1px solid #bbb;padding:4px 6px;vertical-align:top'
                if bg:
                    css += ';background:%s' % bg
                attrs.append('style="%s"' % css)
                tx = tc.find('a:txBody', NS)
                cell_html = ''
                if tx is not None:
                    cell_html, base, _plain = self._text_html(ctx, None, tx, None, rels)
                    if base.get('size') and base_size is None:
                        base_size = base['size']
                cells.append('<td %s>%s</td>' % (' '.join(attrs), cell_html))
            rows_html.append('<tr>%s</tr>' % ''.join(cells))
        cols = ''.join('<col style="width:%.1f%%"/>' % (w * 100 / total) for w in widths)
        table = ('<table style="width:100%%;border-collapse:collapse"><colgroup>%s</colgroup>%s</table>'
                 % (cols, ''.join(rows_html)))
        elements.append({
            'id': _new_id(), 'type': 'text', **geom, 'required': False,
            'props': {'html': table, 'valign': 'top', 'role': ''},
            'style': {'fontSize': round((base_size or 14) * 96 / 72 * self.scale)},
        })

    def _walk(self, ctx, parent, transform, rels, elements, from_layout=False):
        for node in parent:
            if not isinstance(node.tag, str):
                continue
            tag = etree.QName(node).localname
            if tag == 'AlternateContent':
                fallback = node.find('mc:Fallback', NS)
                if fallback is not None:
                    self._walk(ctx, fallback, transform, rels, elements, from_layout)
                continue
            if tag in ('sp', 'cxnSp'):
                self._convert_sp(ctx, node, transform, rels, elements, from_layout)
            elif tag == 'pic':
                self._convert_pic(ctx, node, transform, rels, elements)
            elif tag == 'grpSp':
                xfrm = node.find('p:grpSpPr/a:xfrm', NS)
                box = self._box(xfrm)
                ch_off = xfrm.find('a:chOff', NS) if xfrm is not None else None
                ch_ext = xfrm.find('a:chExt', NS) if xfrm is not None else None
                if box and ch_off is not None and ch_ext is not None:
                    cx, cy = int(ch_off.get('x')), int(ch_off.get('y'))
                    cw, ch = int(ch_ext.get('cx')) or 1, int(ch_ext.get('cy')) or 1
                    sx, sy = box['w'] / cw, box['h'] / ch

                    def group_transform(x, y, w, h, _b=box, _cx=cx, _cy=cy, _sx=sx, _sy=sy,
                                        _outer=transform):
                        return _outer(_b['x'] + (x - _cx) * _sx, _b['y'] + (y - _cy) * _sy,
                                      w * _sx, h * _sy)
                    self._walk(ctx, node, group_transform, rels, elements, from_layout)
                else:
                    self._walk(ctx, node, transform, rels, elements, from_layout)
            elif tag == 'graphicFrame':
                data = node.find('a:graphic/a:graphicData', NS)
                uri = data.get('uri', '') if data is not None else ''
                if uri.endswith('/table'):
                    self._convert_table(ctx, node, transform, rels, elements)
                elif not from_layout:
                    kind = 'chart' if 'chart' in uri else ('SmartArt diagram' if 'diagram' in uri
                                                             else 'embedded object')
                    self.warnings.append('Slide %d: a %s could not be converted - add it again '
                                         'as a picture.' % (ctx['number'], kind))

    def _background(self, trees):
        for tree, part in trees:
            if tree is None:
                continue
            bg = tree.find('p:cSld/p:bg', NS)
            if bg is None:
                continue
            bg_pr = bg.find('p:bgPr', NS)
            if bg_pr is not None:
                blip = bg_pr.find('a:blipFill/a:blip', NS)
                if blip is not None:
                    rel = self._rels(part).get(blip.get(R_EMBED))
                    if rel and not rel[2]:
                        key = self._media(rel[0], WEB_IMAGE_TYPES, 'background picture')
                        if key:
                            return None, key
                color, _m = self._fill(bg_pr)
                if color:
                    return color, None
            bg_ref = bg.find('p:bgRef', NS)
            if bg_ref is not None:
                color = self._color(bg_ref)
                if color:
                    return color, None
        return None, None

    def _notes(self, slide_part):
        notes_part = self._rel_of_type(slide_part, 'notesSlide')
        tree = self._read(notes_part) if notes_part else None
        if tree is None:
            return ''
        texts = []
        for sp in tree.iterfind('.//p:sp', NS):
            ph = self._placeholder(sp)
            if ph and ph['type'] == 'body':
                for para in sp.findall('p:txBody/a:p', NS):
                    texts.append(''.join(t.text or '' for t in para.iter('{%s}t' % NS['a'])))
        return '\n'.join(texts).strip()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def convert(self):
        if self.zip is None:
            self.validate()
        pres = self._read('ppt/presentation.xml')
        size = pres.find('p:sldSz', NS)
        cx = int(size.get('cx', '12192000')) if size is not None else 12192000
        cy = int(size.get('cy', '6858000')) if size is not None else 6858000
        self.scale = self.target_width / (cx / EMU_PER_PX)
        width = self.target_width
        height = round(cy / EMU_PER_PX * self.scale)

        def identity(x, y, w, h):
            return x, y, w, h

        slides = []
        skipped_hidden = 0
        for number, part in enumerate(self._slide_parts(), start=1):
            tree = self._read(part)
            if tree is None:
                self.warnings.append('Slide %d could not be read and was skipped.' % number)
                continue
            if tree.get('show') == '0':
                skipped_hidden += 1
                continue
            layout_part = self._rel_of_type(part, 'slideLayout')
            layout = self._read(layout_part) if layout_part else None
            master_part = self._rel_of_type(layout_part, 'slideMaster') if layout_part else None
            master = self._read(master_part) if master_part else None
            if master_part:
                self.theme_colors, self.theme_fonts = self._load_theme(master_part)
            ctx = {'layout': layout, 'master': master, 'number': number, 'title': '',
                   'custom_shapes': 0}

            elements = []
            show_master = tree.get('showMasterSp') != '0'
            layout_shows_master = layout is None or layout.get('showMasterSp') != '0'
            if show_master:
                if master is not None and layout_shows_master:
                    self._walk(ctx, master.find('p:cSld/p:spTree', NS), identity,
                               self._rels(master_part), elements, from_layout=True)
                if layout is not None:
                    self._walk(ctx, layout.find('p:cSld/p:spTree', NS), identity,
                               self._rels(layout_part), elements, from_layout=True)
            self._walk(ctx, tree.find('p:cSld/p:spTree', NS), identity, self._rels(part), elements)
            for z, element in enumerate(elements, start=1):
                element['z'] = z

            bg_color, bg_media = self._background(
                [(tree, part), (layout, layout_part), (master, master_part)])
            if ctx['custom_shapes']:
                self.warnings.append('Slide %d: %d shape(s) with special outlines were converted '
                                     'to rectangles.' % (number, ctx['custom_shapes']))
            slides.append({
                'name': ctx['title'] or 'Slide %d' % number,
                'notes': self._notes(part),
                'background_color': bg_color if bg_color and bg_color.startswith('#') else '',
                'background_css': bg_color if bg_color and not bg_color.startswith('#') else '',
                'background_media': bg_media,
                'elements': elements,
            })
        if skipped_hidden:
            self.warnings.append('%d hidden slide(s) were skipped.' % skipped_hidden)
        return {
            'width': width,
            'height': height,
            'slides': slides,
            'media': self.media,
            'warnings': self.warnings,
        }


GOOGLE_SLIDES_RE = re.compile(r'docs\.google\.com/presentation/(?:u/\d+/)?d/(?:e/)?([A-Za-z0-9_-]{20,})')


def google_slides_export_url(url):
    """Return the .pptx export URL for a Google Slides link, or None."""
    match = GOOGLE_SLIDES_RE.search(url or '')
    if not match or '/d/e/' in (url or ''):
        return None
    return 'https://docs.google.com/presentation/d/%s/export/pptx' % match.group(1)

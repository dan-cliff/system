"""Server-side SVG rendering of a Risk's bowtie diagram.

The same SVG is shown in the in-app "Bowtie Diagram" dialog and embedded in the
Risk Assessment PDF appendices, so it only uses plain SVG 1.1 that wkhtmltopdf's
renderer understands (no foreignObject, no CSS text wrapping): text is wrapped
here, by an approximate character count, into <tspan> lines.
"""
import re
import textwrap

from markupsafe import Markup, escape

FONT = 'Helvetica, Arial, sans-serif'
MARGIN = 20
END_W = 170        # threat / consequence boxes
BOX_W = 150        # barrier boxes
ESC_W = 136        # escalation factor (and its barriers) boxes
GAP = 24           # between barrier columns
FAN = 70           # space where the rows converge on the top event
ROW_GAP = 22
RADIUS = 72        # top event circle
HAZARD_W = 220
LEGEND_H = 46

THREAT_FILL = '#1c64b4'
CONSEQUENCE_FILL = '#c92a2a'
TOP_EVENT_FILL = '#e8590c'
ESCALATION_FILL = '#ffe066'
NO_EFFECTIVENESS = '#adb5bd'


def _wrap(text, width_px, font_size, max_lines=6):
    text = ' '.join((text or '').split())
    if not text:
        return []
    chars = max(6, int(width_px / (font_size * 0.56)))
    lines = textwrap.wrap(text, chars, break_long_words=True) or ['']
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(1, chars - 1)].rstrip() + '…'
    return lines


def _safe_colour(value, default=NO_EFFECTIVENESS):
    """Only let well-formed hex colours into the SVG's attributes."""
    value = (value or '').strip()
    return value if re.fullmatch(r'#(?:[0-9a-fA-F]{3}){1,2}', value) else default


def _text_colour(hex_colour):
    """Black or white, whichever reads better on the given background."""
    value = (hex_colour or '').lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return '#000000'
    return '#000000' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#ffffff'


def _text(lines, cx, top, font_size, fill, bold=False, line_h=None):
    """Centred multi-line text whose first line's box starts at ``top``."""
    if not lines:
        return ''
    line_h = line_h or round(font_size * 1.25)
    baseline = top + font_size * 0.85
    weight = ' font-weight="bold"' if bold else ''
    spans = ''.join(
        '<tspan x="%s" y="%s">%s</tspan>' % (cx, round(baseline + i * line_h, 1), escape(line))
        for i, line in enumerate(lines)
    )
    return '<text font-family="%s" font-size="%s" fill="%s" text-anchor="middle"%s>%s</text>' % (
        FONT, font_size, fill, weight, spans,
    )


class _Box:
    """A measured box: knows its size before it is positioned, draws itself once placed."""

    def __init__(self, width, height, draw):
        self.width = width
        self.height = height
        self._draw = draw

    def draw(self, x, y):
        return self._draw(x, y)


def _end_box(name, fill, subtitle=None):
    lines = _wrap(name, END_W - 16, 12)
    sub = _wrap(subtitle, END_W - 16, 10, max_lines=2) if subtitle else []
    height = 12 + len(lines) * 15 + (len(sub) * 13 + 4 if sub else 0) + 10
    height = max(height, 44)

    def draw(x, y):
        cx = x + END_W / 2
        text_h = len(lines) * 15 + (len(sub) * 13 + 4 if sub else 0)
        top = y + (height - text_h) / 2
        out = '<rect x="%s" y="%s" width="%s" height="%s" rx="6" fill="%s"/>' % (x, y, END_W, height, fill)
        out += _text(lines, cx, top, 12, '#ffffff', bold=True, line_h=15)
        if sub:
            out += _text(sub, cx, top + len(lines) * 15 + 4, 10, '#ffffff', line_h=13)
        return out

    return _Box(END_W, height, draw)


def _barrier_box(barrier, width, font_size=12):
    colour = _safe_colour(barrier.effectiveness_color)
    strip_label = barrier.effectiveness_id.name or 'Effectiveness not set'
    strip_h = 16
    line_h = round(font_size * 1.25)
    lines = _wrap(barrier.name, width - 12, font_size)
    meta = [value for value in (barrier.barrier_type_id.name, barrier.accountable) if value]
    meta_lines = [_wrap(value, width - 12, 9.5, max_lines=1)[0] for value in meta]
    height = strip_h + 6 + len(lines) * line_h + (len(meta_lines) * 12 + 2 if meta_lines else 0) + 6

    def draw(x, y):
        cx = x + width / 2
        out = '<rect x="%s" y="%s" width="%s" height="%s" rx="3" fill="#ffffff" stroke="#343a40" stroke-width="1.2"/>' % (
            x, y, width, height)
        out += '<rect x="%s" y="%s" width="%s" height="%s" rx="3" fill="%s" stroke="#343a40" stroke-width="1.2"/>' % (
            x, y, width, strip_h, colour)
        out += _text(_wrap(strip_label, width - 8, 9.5, max_lines=1), cx, y + 3, 9.5, _text_colour(colour), bold=True)
        top = y + strip_h + 6
        out += _text(lines, cx, top, font_size, '#212529', line_h=line_h)
        if meta_lines:
            out += _text(meta_lines, cx, top + len(lines) * line_h + 2, 9.5, '#495057', line_h=12)
        return out

    return _Box(width, height, draw)


def _escalation_block(factor):
    """An escalation factor box with its own barriers stacked underneath it."""
    lines = _wrap(factor.name, ESC_W - 12, 11)
    factor_h = 16 + 6 + len(lines) * 14 + 6
    barriers = [_barrier_box(barrier, ESC_W, font_size=11) for barrier in factor.barrier_ids]
    height = factor_h + sum(10 + box.height for box in barriers)

    def draw(x, y):
        cx = x + ESC_W / 2
        out = '<rect x="%s" y="%s" width="%s" height="%s" rx="3" fill="%s" stroke="#b08900" stroke-width="1.2"/>' % (
            x, y, ESC_W, factor_h, ESCALATION_FILL)
        out += _text(['Escalation Factor'], cx, y + 4, 9.5, '#5c4400', bold=True)
        out += _text(lines, cx, y + 22, 11, '#212529', line_h=14)
        cursor = y + factor_h
        for box in barriers:
            out += '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#b08900" stroke-width="1.2"/>' % (
                cx, cursor, cx, cursor + 10)
            out += box.draw(x, cursor + 10)
            cursor += 10 + box.height
        return out

    return _Box(ESC_W, height, draw)


class _Row:
    """One threat (or consequence) with its barriers and their escalation factors."""

    def __init__(self, end_box, barriers):
        self.end_box = end_box
        self.barriers = []
        for barrier in barriers:
            box = _barrier_box(barrier, BOX_W)
            blocks = [_escalation_block(factor) for factor in barrier.escalation_factor_ids]
            self.barriers.append((box, blocks))
        self.axis = max([end_box.height] + [box.height for box, _ in self.barriers]) / 2
        bottoms = [end_box.height]
        for box, blocks in self.barriers:
            bottoms.append(self.axis + box.height / 2 + sum(14 + block.height for block in blocks))
        self.height = max(bottoms)

    def draw(self, top, end_x, barrier_xs, line_from_x, line_to_x, target):
        """Draw the row with its axis at ``top + axis``, joining the line to ``target``."""
        axis_y = top + self.axis
        fan_mid = (line_to_x + target[0]) / 2
        out = '<path d="M %s %s L %s %s C %s %s %s %s %s %s" fill="none" stroke="#495057" stroke-width="2"/>' % (
            line_from_x, axis_y, line_to_x, axis_y,
            fan_mid, axis_y, fan_mid, target[1], target[0], target[1],
        )
        out += self.end_box.draw(end_x, top + self.axis - self.end_box.height / 2)
        for (box, blocks), x in zip(self.barriers, barrier_xs):
            box_y = axis_y - box.height / 2
            out += box.draw(x, box_y)
            cursor = box_y + box.height
            for block in blocks:
                cx = x + BOX_W / 2
                out += '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#b08900" stroke-width="1.5" stroke-dasharray="4,3"/>' % (
                    cx, cursor, cx, cursor + 14)
                out += block.draw(x + (BOX_W - ESC_W) / 2, cursor + 14)
                cursor += 14 + block.height
        return out


def _stack_height(rows):
    return sum(row.height for row in rows) + ROW_GAP * max(0, len(rows) - 1)


def _legend(y, width, effectiveness):
    items = [
        ('rect', THREAT_FILL, 'Threat'),
        ('barrier', NO_EFFECTIVENESS, 'Barrier'),
        ('circle', TOP_EVENT_FILL, 'Top Event'),
        ('rect', CONSEQUENCE_FILL, 'Consequence'),
        ('rect', ESCALATION_FILL, 'Escalation Factor'),
    ] + [('swatch', colour, name) for name, colour in effectiveness]
    out = '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#dee2e6"/>' % (MARGIN, y, width - MARGIN, y)
    x = MARGIN
    row_y = y + 14
    for kind, colour, label in items:
        label_w = len(label) * 6.2 + 34
        if x + label_w > width - MARGIN:
            x = MARGIN
            row_y += 18
        if kind == 'circle':
            out += '<circle cx="%s" cy="%s" r="6" fill="%s"/>' % (x + 7, row_y + 6, colour)
        elif kind == 'barrier':
            out += '<rect x="%s" y="%s" width="14" height="12" fill="#ffffff" stroke="#343a40"/>' % (x, row_y)
        else:
            stroke = ' stroke="#b08900"' if colour == ESCALATION_FILL else ''
            out += '<rect x="%s" y="%s" width="14" height="12" rx="2" fill="%s"%s/>' % (x, row_y, colour, stroke)
        out += '<text x="%s" y="%s" font-family="%s" font-size="10.5" fill="#343a40">%s</text>' % (
            x + 20, row_y + 10, FONT, escape(label))
        x += label_w
    return out, row_y + 18 - y


def render_bowtie_svg(line):
    """Return the bowtie diagram of a risk.line.mixin record as an SVG Markup string."""
    threats = line.bowtie_threat_ids
    consequences = line.bowtie_consequence_ids
    left_rows = [_Row(_end_box(threat.name, THREAT_FILL), threat.barrier_ids) for threat in threats]
    right_rows = [
        _Row(
            _end_box(
                consequence.name, CONSEQUENCE_FILL,
                consequence.consequence_id and 'Severity: %s' % consequence.consequence_id.name,
            ),
            consequence.barrier_ids,
        )
        for consequence in consequences
    ]
    left_cols = max([len(row.barriers) for row in left_rows] or [0])
    right_cols = max([len(row.barriers) for row in right_rows] or [0])

    left_w = END_W + left_cols * (BOX_W + GAP) + GAP
    right_w = END_W + right_cols * (BOX_W + GAP) + GAP
    center_w = max(2 * RADIUS, HAZARD_W) + 20

    hazard_lines = _wrap(line.unwanted_event, HAZARD_W - 24, 12, max_lines=4)
    hazard_h = (30 + len(hazard_lines) * 15 + 12) if hazard_lines else 0
    hazard_gap = 30 if hazard_lines else 0
    content_h = max(_stack_height(left_rows), _stack_height(right_rows), 2 * RADIUS) + 2 * MARGIN

    width = 2 * MARGIN + left_w + 2 * FAN + center_w + right_w
    cx = MARGIN + left_w + FAN + center_w / 2
    cy = content_h / 2
    if hazard_lines:
        # Push the top event down if centring it would clip the hazard box.
        cy = max(cy, MARGIN + hazard_h + hazard_gap + RADIUS)
        content_h = max(content_h, cy + RADIUS + MARGIN)

    effectiveness = []
    seen = set()
    for barrier in (
        threats.barrier_ids | consequences.barrier_ids
        | threats.barrier_ids.escalation_factor_ids.barrier_ids
        | consequences.barrier_ids.escalation_factor_ids.barrier_ids
    ).sorted(lambda b: (b.effectiveness_id.sequence, b.effectiveness_id.id)):
        if barrier.effectiveness_id and barrier.effectiveness_id not in seen:
            seen.add(barrier.effectiveness_id)
            effectiveness.append((barrier.effectiveness_id.name, _safe_colour(barrier.effectiveness_color)))

    body = ''
    # Left side: threat -> preventive barriers -> top event.
    top = (content_h - _stack_height(left_rows)) / 2
    barrier_xs = [MARGIN + END_W + GAP + i * (BOX_W + GAP) for i in range(left_cols)]
    for row in left_rows:
        body += row.draw(
            top, MARGIN, barrier_xs, MARGIN + END_W, MARGIN + left_w, (cx - RADIUS, cy),
        )
        top += row.height + ROW_GAP
    # Right side: top event -> recovery barriers -> consequence, mirrored.
    right_x0 = cx + center_w / 2 + FAN
    top = (content_h - _stack_height(right_rows)) / 2
    barrier_xs = [right_x0 + GAP + i * (BOX_W + GAP) for i in range(right_cols)]
    end_x = right_x0 + right_w - END_W
    for row in right_rows:
        body += row.draw(top, end_x, barrier_xs, end_x, right_x0, (cx + RADIUS, cy))
        top += row.height + ROW_GAP

    pattern_id = 'o_bowtie_hazard_%s_%s' % (line._name.replace('.', '_'), line.id or 0)
    if hazard_lines:
        hx = cx - HAZARD_W / 2
        hy = cy - RADIUS - hazard_gap - hazard_h
        body += '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#495057" stroke-width="2"/>' % (
            cx, hy + hazard_h, cx, cy - RADIUS)
        body += '<rect x="%s" y="%s" width="%s" height="%s" fill="url(#%s)"/>' % (
            hx, hy, HAZARD_W, hazard_h, pattern_id)
        body += '<rect x="%s" y="%s" width="%s" height="%s" fill="#ffffff"/>' % (
            hx + 6, hy + 6, HAZARD_W - 12, hazard_h - 12)
        body += _text(['HAZARD'], cx, hy + 11, 10, '#212529', bold=True)
        body += _text(hazard_lines, cx, hy + 28, 12, '#212529', line_h=15)

    top_lines = _wrap(line.name, 2 * RADIUS - 24, 12, max_lines=5)
    body += '<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="#a61e4d" stroke-width="2"/>' % (
        cx, cy, RADIUS, TOP_EVENT_FILL)
    label_h = 14 + len(top_lines) * 15
    body += _text(['TOP EVENT'], cx, cy - label_h / 2, 9.5, '#ffffff', bold=True)
    body += _text(top_lines, cx, cy - label_h / 2 + 14, 12, '#ffffff', bold=True, line_h=15)

    legend, legend_h = _legend(content_h, width, effectiveness)
    height = content_h + max(LEGEND_H, legend_h)
    defs = (
        '<defs><pattern id="%s" patternUnits="userSpaceOnUse" width="14" height="14" '
        'patternTransform="rotate(45)"><rect width="7" height="14" fill="#fcc419"/>'
        '<rect x="7" width="7" height="14" fill="#212529"/></pattern></defs>' % pattern_id
    )
    return Markup(
        '<svg xmlns="http://www.w3.org/2000/svg" class="o_risk_bowtie_svg" viewBox="0 0 %s %s" '
        'width="%s" height="%s" preserveAspectRatio="xMidYMin meet">'
        '<rect width="100%%" height="100%%" fill="#ffffff"/>%s%s%s</svg>'
    ) % (round(width), round(height), round(width), round(height), Markup(defs), Markup(body), Markup(legend))

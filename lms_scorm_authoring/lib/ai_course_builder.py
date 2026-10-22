"""Turn an AI-written course outline into editor slides.

The AI answers with ``COURSE_SCHEMA``: titles, text, interactions and
questions, but no layout. ``build_slides`` lays each one out on the course's
slide size using the same element structure as the editor and the player, so
the author can carry on editing the result.
"""
import html
import uuid

QUESTION_KINDS = ('mcq', 'mrq', 'truefalse')
INTERACTIONS = ('none', 'tabs', 'accordion', 'flip_cards')

_QUESTION = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': list(QUESTION_KINDS)},
        'prompt': {'type': 'string'},
        'options': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'text': {'type': 'string'}, 'correct': {'type': 'boolean'}},
                'required': ['text', 'correct'],
                'additionalProperties': False,
            },
        },
        'feedback_correct': {'type': 'string'},
        'feedback_incorrect': {'type': 'string'},
    },
    'required': ['type', 'prompt', 'options', 'feedback_correct', 'feedback_incorrect'],
    'additionalProperties': False,
}

COURSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string'},
        'slides': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'kind': {'type': 'string', 'enum': ['title', 'content', 'interaction', 'knowledge_check']},
                    'title': {'type': 'string'},
                    'paragraphs': {'type': 'array', 'items': {'type': 'string'}},
                    'bullets': {'type': 'array', 'items': {'type': 'string'}},
                    'interaction': {'type': 'string', 'enum': list(INTERACTIONS)},
                    'items': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {'title': {'type': 'string'}, 'text': {'type': 'string'}},
                            'required': ['title', 'text'],
                            'additionalProperties': False,
                        },
                    },
                    'question': _QUESTION,
                    'notes': {'type': 'string'},
                },
                'required': ['kind', 'title', 'paragraphs', 'bullets', 'interaction', 'items',
                             'question', 'notes'],
                'additionalProperties': False,
            },
        },
        'exam': {'type': 'array', 'items': _QUESTION},
    },
    'required': ['title', 'description', 'slides', 'exam'],
    'additionalProperties': False,
}


def plan_course(minutes, include_checks, include_exam):
    """How much to ask for, from the course length in minutes."""
    minutes = max(5, min(int(minutes or 15), 240))
    content = max(3, min(round(minutes * 0.75), 60))
    checks = max(1, content // 4) if include_checks else 0
    exam = max(5, min(round(minutes / 3), 20)) if include_exam else 0
    return {'minutes': minutes, 'content_slides': content, 'knowledge_checks': checks,
            'exam_questions': exam}


def _id():
    return 'e' + uuid.uuid4().hex[:10]


def _clean(text, limit=4000):
    return (text or '').strip()[:limit]


def _paragraphs_html(paragraphs, bullets=(), align=None):
    style = ' style="text-align:%s"' % align if align else ''
    parts = ['<p%s>%s</p>' % (style, html.escape(_clean(p))) for p in paragraphs if _clean(p)]
    items = [html.escape(_clean(b, 500)) for b in bullets if _clean(b, 500)]
    if items:
        parts.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % item for item in items))
    return ''.join(parts)


def _question_element(question, box, scored, attempts):
    """A question element, or None when the question can't be answered."""
    if not isinstance(question, dict):
        return None
    kind = question.get('type') if question.get('type') in QUESTION_KINDS else 'mcq'
    options = [{'text': _clean(o.get('text'), 300), 'correct': bool(o.get('correct'))}
               for o in question.get('options') or [] if isinstance(o, dict) and _clean(o.get('text'), 300)]
    prompt = _clean(question.get('prompt'), 1000)
    if not prompt or len(options) < 2 or not any(o['correct'] for o in options):
        return None
    if kind != 'mrq':
        # One right answer: keep the first one marked correct
        seen = False
        for option in options:
            option['correct'] = option['correct'] and not seen
            seen = seen or option['correct']
    rows = len(options)
    return {
        'id': _id(), 'type': kind, **box, 'z': 2, 'rotation': 0, 'required': True, 'scored': scored,
        'props': {
            'prompt': '<p>%s</p>' % html.escape(prompt),
            'options': options[:8],
            'attempts': attempts,
            'shuffle': kind != 'truefalse',
            'points': 1,
            'feedback_correct': _paragraphs_html([question.get('feedback_correct')]),
            'feedback_incorrect': _paragraphs_html([question.get('feedback_incorrect')]),
        },
        'style': {'fontSize': 22 if rows <= 4 else 20},
    }


def build_slides(answer, width, height, include_checks, include_exam, passing_score=80):
    """Return (slides, warnings) for ``lms.scorm.slide`` from the AI's answer."""
    W, H = width, height
    margin = round(W * 0.06)
    inner = W - 2 * margin
    head_h = round(H * 0.13)
    body_top = round(H * 0.06) + head_h + round(H * 0.03)
    body_h = H - body_top - round(H * 0.07)
    slides, warnings = [], []
    scored_checks = include_checks and not include_exam

    def heading(text, y=None, size=40, align=None, h=None):
        return {
            'id': _id(), 'type': 'text', 'x': margin, 'y': round(H * 0.06) if y is None else y,
            'w': inner, 'h': h or head_h, 'z': 2, 'rotation': 0, 'required': False,
            'props': {'html': _paragraphs_html([text], align=align), 'valign': 'middle', 'role': 'title'},
            'style': {'fontSize': size, 'bold': True},
        }

    def accent(y):
        return {'id': _id(), 'type': 'shape', 'x': margin, 'y': y, 'w': round(W * 0.08), 'h': 6,
                'z': 1, 'rotation': 0, 'required': False, 'props': {'shape': 'rect'},
                'style': {'radius': 3}}

    def text(html_value, x, y, w, h, size=24, style=None):
        return {'id': _id(), 'type': 'text', 'x': x, 'y': y, 'w': w, 'h': h, 'z': 2, 'rotation': 0,
                'required': False, 'props': {'html': html_value, 'valign': 'top'},
                'style': dict({'fontSize': size}, **(style or {}))}

    def slide(name, elements, notes='', **gate):
        slides.append({
            'name': _clean(name, 200) or 'Slide %d' % (len(slides) + 1),
            'notes': _clean(notes, 8000),
            'elements': elements,
            'gate_require_interactions': gate.get('gate_require_interactions', True),
            'gate_min_seconds': gate.get('min_seconds', 0),
            'gate_pass_score': 0,
            'gate_max_attempts': 0,
        })

    for item in (answer or {}).get('slides') or []:
        if not isinstance(item, dict):
            continue
        kind = item.get('kind')
        title = _clean(item.get('title'), 200)
        paragraphs = [p for p in item.get('paragraphs') or [] if isinstance(p, str)]
        bullets = [b for b in item.get('bullets') or [] if isinstance(b, str)]
        notes = item.get('notes') or ''

        if kind == 'title':
            y = round(H * 0.3)
            elements = [heading(title, y=y, size=54, align='center', h=round(H * 0.16))]
            elements.append(dict(accent(y + round(H * 0.17)), x=round((W - W * 0.08) / 2)))
            if paragraphs:
                elements.append(text(_paragraphs_html(paragraphs[:2], align='center'), margin,
                                     y + round(H * 0.21), inner, round(H * 0.25), size=26))
            slide(title, elements, notes)

        elif kind == 'knowledge_check':
            question = _question_element(
                item.get('question'), {'x': margin + round(inner * 0.08), 'y': body_top,
                                       'w': round(inner * 0.84), 'h': body_h},
                scored=scored_checks, attempts=2)
            if not question:
                warnings.append('A knowledge check on "%s" had no usable answers and was left out.' % title)
                continue
            slide(title or 'Knowledge check', [heading(title or 'Knowledge check'),
                                               accent(round(H * 0.06) + head_h), question], notes)

        elif kind == 'interaction' and item.get('interaction') in ('tabs', 'accordion', 'flip_cards') \
                and len([i for i in item.get('items') or [] if isinstance(i, dict)]) >= 2:
            entries = [i for i in item['items'] if isinstance(i, dict) and _clean(i.get('title'), 200)][:6]
            elements = [heading(title), accent(round(H * 0.06) + head_h)]
            top = body_top
            if paragraphs:
                intro_h = round(H * 0.1)
                elements.append(text(_paragraphs_html(paragraphs[:1]), margin, top, inner, intro_h, size=22))
                top += intro_h + round(H * 0.02)
            area_h = H - top - round(H * 0.07)
            kind_ = item['interaction']
            if kind_ == 'flip_cards':
                count = min(len(entries), 4)
                gap = round(W * 0.02)
                card_w = round((inner - gap * (count - 1)) / count)
                card_h = min(area_h, round(card_w * 0.85))
                for index, entry in enumerate(entries[:count]):
                    elements.append({
                        'id': _id(), 'type': 'flipcard', 'x': margin + index * (card_w + gap), 'y': top,
                        'w': card_w, 'h': card_h, 'z': 2, 'rotation': 0, 'required': True,
                        'props': {'front_html': '<p><strong>%s</strong></p>' % html.escape(_clean(entry.get('title'), 200)),
                                  'back_html': _paragraphs_html([entry.get('text')]), 'back_background': ''},
                        'style': {'fontSize': 22 if count <= 3 else 19, 'radius': 12},
                    })
            else:
                elements.append({
                    'id': _id(), 'type': 'tabs' if kind_ == 'tabs' else 'accordion',
                    'x': margin, 'y': top, 'w': inner, 'h': area_h, 'z': 2, 'rotation': 0, 'required': True,
                    'props': {'items': [{'title': _clean(e.get('title'), 120),
                                         'html': _paragraphs_html([e.get('text')])} for e in entries]},
                    'style': {'fontSize': 20},
                })
            slide(title, elements, notes)

        else:
            # Content (also the fallback for anything the AI got wrong)
            elements = [heading(title), accent(round(H * 0.06) + head_h)]
            if paragraphs and bullets:
                col = round(inner * 0.5)
                elements.append(text(_paragraphs_html(paragraphs), margin, body_top, col - round(W * 0.02), body_h))
                elements.append(text(_paragraphs_html([], bullets), margin + col, body_top, inner - col, body_h,
                                     size=22, style={'background': '#f3f6fb', 'radius': 12, 'padding': 20}))
            elif paragraphs or bullets:
                elements.append(text(_paragraphs_html(paragraphs, bullets), margin, body_top, inner, body_h))
            else:
                continue
            slide(title, elements, notes)

    exam = [q for q in (answer or {}).get('exam') or [] if isinstance(q, dict)] if include_exam else []
    exam_elements = []
    for question in exam:
        element = _question_element(question, {'x': margin + round(inner * 0.08), 'y': body_top,
                                               'w': round(inner * 0.84), 'h': body_h},
                                    scored=True, attempts=1)
        if element:
            exam_elements.append(element)
        else:
            warnings.append('An exam question had no usable answers and was left out.')
    if exam_elements:
        slide('Final assessment', [
            heading('Final assessment', y=round(H * 0.28), size=48, align='center'),
            text(_paragraphs_html([
                'Answer the next %d questions. You need %d%% to pass.' % (len(exam_elements), passing_score),
                'You have one attempt at each question.',
            ], align='center'), margin, round(H * 0.45), inner, round(H * 0.25), size=26),
        ], gate_require_interactions=False)
        for number, element in enumerate(exam_elements, start=1):
            title = 'Question %d of %d' % (number, len(exam_elements))
            slide(title, [heading(title), accent(round(H * 0.06) + head_h), element])

    if exam_elements or (scored_checks and any(
            el.get('scored') for s in slides for el in s['elements'])):
        slide('Your results', [
            heading('Your results', align='center'),
            {'id': _id(), 'type': 'results', 'x': round(W * 0.2), 'y': body_top, 'w': round(W * 0.6),
             'h': round(H * 0.55), 'z': 2, 'rotation': 0, 'required': False,
             'props': {'pass_html': '', 'fail_html': '', 'allow_retry': True}, 'style': {}},
        ])
    return slides, warnings

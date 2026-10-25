# -*- coding: utf-8 -*-
"""Public submission pages (see models/checklist_public.py).

    GET  /checklists/public/<token>   the template's form, filled in from the link
    POST /checklists/public/<token>   submit it (the link's query string is kept,
                                      so locked values are read from it again)
"""
import json

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.mail import email_normalize

from ..models.checklist_public import CONTACT_KEYS, TZ_KEY, question_key
from ..models.checklist_question_condition import MULTI_OPTION_TYPES
from ..models.checklist_template import FULL_WIDTH_TYPES, LAYOUT_TYPES, RELATION_TYPES

# Hidden field people never fill in: a value means a bot sent the form.
HONEYPOT = 'website_url'


class ChecklistPublicController(http.Controller):

    def _public_template(self, token):
        if not token:
            return None
        return request.env['checklist.template'].sudo().search(
            [('public_token', '=', token), ('public_enabled', '=', True)], limit=1) or None

    def _unavailable(self):
        return request.render('checklists.public_checklist_unavailable', {}, status=404)

    @http.route('/checklists/public/<string:token>', type='http', auth='public', methods=['GET'],
                sitemap=False)
    def public_form(self, token, **kwargs):
        template = self._public_template(token)
        if not template:
            return self._unavailable()
        values, locked, _trusted = template._public_read_link(request.httprequest.args)
        return self._render_form(template, values, locked, {})

    @http.route('/checklists/public/<string:token>', type='http', auth='public', methods=['POST'],
                csrf=True, sitemap=False)
    def public_submit(self, token, **kwargs):
        template = self._public_template(token)
        if not template:
            return self._unavailable()
        link_values, locked, _trusted = template._public_read_link(request.httprequest.args)
        form = request.httprequest.form
        if form.get(HONEYPOT):
            return request.render('checklists.public_checklist_done', {'template': template, 'checklist': None})
        tz_name = link_values.get(TZ_KEY) or form.get('_tz')

        posted, errors = {}, {}
        for key in CONTACT_KEYS:
            posted[key] = link_values.get(key, '') if key in locked else (form.get(key) or '').strip()
        contact = dict(posted)
        if not contact['first_name']:
            errors['first_name'] = request.env._('Enter your first name.')
        if not contact['last_name']:
            errors['last_name'] = request.env._('Enter your last name.')
        if contact['email'] and not email_normalize(contact['email']):
            errors['email'] = request.env._('Enter a valid email address.')
        if not contact['email'] and not contact['phone']:
            errors['contact'] = request.env._('Enter your email address or phone number.')

        answers = {}
        for question in template._public_questions():
            kind = question.question_type
            if kind in LAYOUT_TYPES:
                continue
            key = question_key(question.id)
            if key in locked or kind in RELATION_TYPES:
                # Locked answers, and Many2one / Many2Many ones, only come from a signed link.
                raw = link_values.get(key)
            elif kind in ('image', 'file'):
                raw = request.httprequest.files.get(key)
            elif kind in MULTI_OPTION_TYPES:
                raw = form.getlist(key)
            else:
                # Not sent: an unticked Yes / No, or hidden by its conditions.
                raw = form.get(key)
            if kind not in ('image', 'file'):
                posted[key] = ','.join(raw) if isinstance(raw, list) else (raw or '')
            try:
                answers[question.id] = question._public_line_vals(raw, tz_name)
            except ValidationError as error:
                errors[key] = error.args[0]

        if errors:
            return self._render_form(template, {**link_values, **posted}, locked, errors)
        if contact['phone']:
            contact['phone'] = template._public_format_phone(contact['phone'])
        checklist = template._public_submit(contact, answers)
        return request.render('checklists.public_checklist_done', {'template': template, 'checklist': checklist})

    # ── Rendering ────────────────────────────────────────────────────────

    def _render_form(self, template, values, locked, errors):
        items = []
        conditions = {}
        context = template._public_condition_context()
        for question in template._public_questions():
            key = question_key(question.id)
            raw = values.get(key, '')
            item = {
                'question': question,
                'key': key,
                'type': question.question_type,
                'value': raw,
                'ids': [int(part) for part in raw.split(',') if part.strip().isdigit()],
                'locked': key in locked,
                'error': errors.get(key),
                'full_width': question.question_type in FULL_WIDTH_TYPES,
                'column': question.column if template.column_count != '1' else '1',
            }
            if question.question_type in RELATION_TYPES:
                # Only answered from a signed link: nothing to show otherwise.
                item['display'] = question._public_display(raw)
                if not item['display']:
                    continue
            items.append(item)
            if question.conditional:
                conditions[question.id] = {
                    'logic': question.condition_logic,
                    'rules': question.condition_ids._rule_vals(),
                    'context': context.get(question.id, {}),
                }
        return request.render('checklists.public_checklist_form', {
            'template': template,
            'company': template._public_company(),
            'rows': self._rows(items, int(template.column_count or '1')),
            'column_count': int(template.column_count or '1'),
            'contact': {key: values.get(key, '') for key in CONTACT_KEYS},
            'contact_locked': {key: key in locked for key in CONTACT_KEYS},
            'errors': errors,
            'conditions_json': json.dumps(conditions),
            'types_json': json.dumps({item['question'].id: item['type'] for item in items}),
            'form_action': request.httprequest.full_path.rstrip('?'),
            'tz_link': values.get(TZ_KEY) or '',
        })

    @staticmethod
    def _rows(items, column_count):
        """The form's rows: Section Titles and Breaks span the columns; the
        questions between them sit in their columns, as on the checklist form."""
        rows, block = [], None
        for item in items:
            if item['full_width'] or column_count == 1:
                block = None
                rows.append({'full': item})
                continue
            if block is None:
                block = {'columns': [[] for _ in range(column_count)]}
                rows.append(block)
            index = min(int(item['column'] or '1'), column_count) - 1
            block['columns'][index].append(item)
        return rows

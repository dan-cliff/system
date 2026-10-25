# -*- coding: utf-8 -*-
import json

import pytz

from odoo import http
from odoo.http import request

from odoo.addons.checklists.models.checklist_question_condition import MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES


class TalentQuestionnaire(http.Controller):
    """The screening questionnaire applicants fill in from the email (no login)."""

    def _checklist(self, checklist_id, token):
        checklist = request.env['checklist.checklist'].sudo().browse(checklist_id).exists()
        if not checklist or not checklist.talent_applicant_id or not checklist._talent_check_token(token):
            return None
        return checklist

    @http.route('/talent/questionnaire/<int:checklist_id>/<string:token>', type='http', auth='public',
                methods=['GET'], website=True, sitemap=False)
    def questionnaire(self, checklist_id, token, saved=None, **kwargs):
        checklist = self._checklist(checklist_id, token)
        if not checklist:
            return request.render('modern_recruitment_checklists.questionnaire_invalid', status=404)
        return request.render('modern_recruitment_checklists.questionnaire_page', {
            'checklist': checklist,
            'applicant': checklist.talent_applicant_id,
            'company': checklist.company_id,
            'token': token,
            'saved': bool(saved),
            'items': [self._item(line) for line in checklist._talent_public_lines()],
        })

    @http.route('/talent/questionnaire/<int:checklist_id>/<string:token>', type='http', auth='public',
                methods=['POST'], website=True, sitemap=False)
    def questionnaire_post(self, checklist_id, token, **kwargs):
        checklist = self._checklist(checklist_id, token)
        if not checklist:
            return request.render('modern_recruitment_checklists.questionnaire_invalid', status=404)
        url = '/talent/questionnaire/%s/%s' % (checklist.id, token)
        if checklist.state != 'draft':
            return request.redirect(url)
        form = request.httprequest.form
        checklist._talent_apply_answers(form, request.httprequest.files)
        if form.get('talent_action') == 'submit':
            checklist._talent_submit()
            return request.redirect(url)
        return request.redirect(url + '?saved=1')

    def _item(self, line):
        """A line with what the page shows for it."""
        return {
            'line': line,
            'options': line._talent_options(),
            'value': self._value(line),
            'rules': json.dumps(line.condition_rules or []),
            'context': json.dumps(line.condition_context or {}),
        }

    def _value(self, line):
        kind = line.question_type
        if kind in SINGLE_OPTION_TYPES:
            return line.value_option_id.id
        if kind in MULTI_OPTION_TYPES:
            return line.value_option_ids.ids
        if kind == 'date':
            return line.value_date and line.value_date.strftime('%d/%m/%Y')
        if kind == 'datetime':
            if not line.value_datetime:
                return ''
            tz = line.checklist_id._talent_tz()
            return pytz.utc.localize(line.value_datetime).astimezone(tz).strftime('%d/%m/%Y %H:%M')
        if kind == 'geolocation':
            return (line.value_latitude, line.value_longitude) if (line.value_latitude or line.value_longitude) else None
        if kind == 'image':
            return bool(line.value_image)
        if kind == 'file':
            return line.value_file_name or (bool(line.value_file) and 'file')
        if kind in ('number', 'integer'):
            number = line.value_number if kind == 'number' else line.value_integer
            return number if number else ''
        return {
            'text': line.value_text, 'text_area': line.value_text_area, 'phone': line.value_phone,
            'email': line.value_email, 'website': line.value_url, 'boolean': line.value_boolean,
        }.get(kind) or ''

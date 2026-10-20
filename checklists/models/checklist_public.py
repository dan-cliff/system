# -*- coding: utf-8 -*-
"""Public Link: checklists filled in without signing in.

A template with Public Link on can be opened by anyone at
/checklists/public/<key> (controllers/main.py). Instead of Completed By they
give their Full Name and Email; on submit the contact with that email is
used, or a new one is created, as the checklist's Completed By contact.
"""
import base64
import logging
from datetime import datetime

import pytz

from odoo import Command, api, fields, models, tools
from odoo.exceptions import UserError

from .checklist_question_condition import MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES, eval_domain
from .checklist_template import FULL_WIDTH_TYPES, LAYOUT_TYPES, RELATION_TYPES

_logger = logging.getLogger(__name__)

# Many2one / Many2Many questions list at most this many records on the public form.
PUBLIC_RECORD_LIMIT = 500
TEXT_VALUE_FIELDS = {
    'text': 'value_text', 'text_area': 'value_text_area', 'email': 'value_email', 'website': 'value_url',
}


class Checklist(models.Model):
    _inherit = 'checklist.checklist'

    # ── The public form ──────────────────────────────────────────────────

    @api.model
    def _public_questions(self, template):
        return template.sudo().question_ids

    @api.model
    def _public_relation_records(self, question):
        """(id, name) of the records a Many2one / Many2Many question offers."""
        model = question.relation_model_id.model
        if not model or model not in self.env:
            return []
        try:
            domain = eval_domain(self.env, question.relation_domain)
            records = self.env[model].sudo().search(domain, limit=PUBLIC_RECORD_LIMIT)
        except Exception:  # noqa: BLE001 - a broken filter shows no records rather than an error page
            _logger.warning('Checklist public form: bad filter on question %s', question.id, exc_info=True)
            return []
        return [(record.id, record.display_name) for record in records]

    @api.model
    def _public_form_values(self, template):
        """What the public form template draws: the questions in bands (full
        width sections, or the template's columns), and the data the page's
        script needs to apply the conditions."""
        template = template.sudo()
        questions = self._public_questions(template)
        columns = int(template.column_count or '1')
        # The Current User / Checklist filters, evaluated as the public user
        # on a checklist that is never saved.
        draft = self.sudo().new({
            'template_id': template.id,
            'company_id': self.env.company.id,
            'user_id': False,
            'line_ids': [Command.create(question._checklist_line_vals()) for question in questions],
        })
        contexts = {line.question_id.id: line.condition_context for line in draft.line_ids}
        items, bands, current = [], [], None
        for question in questions:
            item = {
                'question': question,
                'kind': question.question_type,
                'key': 'q_%d' % question.id,
                'options': question.option_ids,
                'records': (self._public_relation_records(question)
                            if question.question_type in RELATION_TYPES else []),
            }
            items.append(item)
            if question.question_type in FULL_WIDTH_TYPES:
                bands.append({'item': item})
                current = None
                continue
            if current is None:
                current = {'columns': [[] for _i in range(columns)]}
                bands.append(current)
            column = min(max(int(question.column or '1'), 1), columns)
            current['columns'][column - 1].append(item)
        script_data = [{
            'id': question.id,
            'question_type': question.question_type,
            'conditional': question.conditional,
            'condition_logic': question.condition_logic,
            'condition_rules': question.condition_ids._rule_vals() if question.conditional else [],
            'condition_context': contexts.get(question.id) or {},
        } for question in questions]
        return {'template': template, 'bands': bands, 'columns': columns, 'script_data': script_data}

    # ── Submitting ───────────────────────────────────────────────────────

    @api.model
    def _public_contact(self, name, email):
        """The contact with this email, or a new one with this name and email."""
        normalized = tools.email_normalize(email)
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('email_normalized', '=', normalized)], order='id', limit=1)
        return partner or Partner.create({'name': name, 'email': normalized})

    @api.model
    def _public_parse_date(self, value):
        try:
            return datetime.strptime(value.strip(), '%d/%m/%Y').date()
        except ValueError:
            raise UserError(self.env._('"%s" is not a date: use dd/mm/yyyy.', value))

    @api.model
    def _public_parse_datetime(self, value, tz_name):
        try:
            local = datetime.strptime(value.strip(), '%d/%m/%Y %H:%M')
        except ValueError:
            raise UserError(self.env._('"%s" is not a date and time: use dd/mm/yyyy HH:MM.', value))
        try:
            tz = pytz.timezone(tz_name or 'UTC')
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _public_line_vals(self, question, form, files):
        """A checklist line for a question, with the answer from the submitted form."""
        vals = question._checklist_line_vals()
        kind, key = question.question_type, 'q_%d' % question.id
        if kind in LAYOUT_TYPES:
            return vals
        value = (form.get(key) or '').strip()
        if kind in TEXT_VALUE_FIELDS:
            vals[TEXT_VALUE_FIELDS[kind]] = value
        elif kind == 'phone' and value:
            country = self.env.company.country_id
            vals['value_phone'] = self.env['checklist.line']._phone_format_number(
                value, country, force_format='INTERNATIONAL') or value
        elif kind in ('number', 'integer') and value:
            try:
                vals['value_number' if kind == 'number' else 'value_integer'] = (
                    float(value) if kind == 'number' else int(value))
            except ValueError:
                raise UserError(self.env._('"%(value)s" is not a number (%(question)s).',
                                           value=value, question=question.name))
        elif kind == 'date' and value:
            vals['value_date'] = self._public_parse_date(value)
        elif kind == 'datetime' and value:
            vals['value_datetime'] = self._public_parse_datetime(value, form.get('tz'))
        elif kind in SINGLE_OPTION_TYPES and value.isdigit():
            if int(value) in question.option_ids.ids:
                vals['value_option_id'] = int(value)
        elif kind in MULTI_OPTION_TYPES:
            chosen = [int(v) for v in form.getlist(key) if v.isdigit()]
            vals['value_option_ids'] = [Command.set([i for i in chosen if i in question.option_ids.ids])]
        elif kind == 'boolean':
            vals['value_boolean'] = bool(value)
        elif kind == 'geolocation':
            try:
                latitude, longitude = float(form.get(key + '_lat') or 0), float(form.get(key + '_lng') or 0)
            except ValueError:
                latitude = longitude = 0.0
            vals.update(value_latitude=latitude, value_longitude=longitude)
        elif kind in ('image', 'file'):
            upload = files.get(key)
            content = upload.read() if upload else b''
            if content:
                vals['value_image' if kind == 'image' else 'value_file'] = base64.b64encode(content)
                if kind == 'file':
                    vals['value_file_name'] = upload.filename
        elif kind in RELATION_TYPES:
            allowed = {record_id for record_id, _name in self._public_relation_records(question)}
            model = question.relation_model_id.model
            if kind == 'many2one' and value.isdigit() and int(value) in allowed:
                vals['value_reference'] = '%s,%s' % (model, int(value))
            elif kind == 'many2many':
                vals['value_reference_ids'] = [int(v) for v in form.getlist(key)
                                               if v.isdigit() and int(v) in allowed]
        return vals

    @api.model
    def _public_submit(self, template, form, files):
        """Create the checklist a public form submitted (form and files are the
        request's MultiDicts). Returns the new checklist."""
        template = template.sudo()
        name = (form.get('submitter_name') or '').strip()
        email = (form.get('submitter_email') or '').strip()
        if not name:
            raise UserError(self.env._('Please enter your Full Name.'))
        if not tools.email_normalize(email):
            raise UserError(self.env._('Please enter a valid Email.'))
        partner = self._public_contact(name, email)
        questions = self._public_questions(template)
        checklist = self.sudo().with_context(mail_create_nosubscribe=True).create({
            'template_id': template.id,
            'company_id': self.env.company.id,
            'user_id': False,
            'partner_id': partner.id,
            'public_submission': True,
            'submitter_name': name,
            'submitter_email': email,
            'column_count': template.column_count,
            'line_ids': [Command.create(self._public_line_vals(question, form, files))
                         for question in questions],
            'state': 'done',
        })
        # GeoLocation answers that show the street address look it up, as on the form.
        for line in checklist.line_ids.filtered(
                lambda l: l.question_type == 'geolocation' and l.geo_show_address
                and (l.value_latitude or l.value_longitude)):
            line.value_address = line.checklist_reverse_geocode(line.value_latitude, line.value_longitude)
        checklist.message_post(
            body=self.env._('Submitted through the Public Link by %(name)s (%(email)s).',
                            name=name, email=email),
            author_id=partner.id,
        )
        return checklist

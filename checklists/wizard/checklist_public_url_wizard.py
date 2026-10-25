# -*- coding: utf-8 -*-
"""Public URL Builder: a public link that fills in chosen fields from its
query string (see models/checklist_public.py). The link is rebuilt as
values are picked, and can be used for any number of submissions."""
import base64
import logging

from odoo import api, fields, models

from ..models.checklist_public import (
    CONTACT_KEYS, LOCK_KEY, NOT_PREFILLABLE_TYPES, TZ_KEY, question_key,
)
from ..models.checklist_question_condition import MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES

_logger = logging.getLogger(__name__)


class ChecklistPublicUrlWizard(models.TransientModel):
    _name = 'checklist.public.url.wizard'
    _description = 'Checklist Public URL Builder'

    template_id = fields.Many2one('checklist.template', string='Template', required=True, ondelete='cascade')
    first_name = fields.Char(string='First Name')
    last_name = fields.Char(string='Last Name')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone Number')
    lock_contact = fields.Boolean(
        string='Lock Contact Details',
        help='The contact details filled in here are shown read-only on the form.',
    )
    line_ids = fields.One2many('checklist.public.url.wizard.line', 'wizard_id', string='Answers')
    url = fields.Char(string='Public URL', compute='_compute_url')
    qr_code = fields.Binary(string='QR Code', compute='_compute_url')

    @api.depends('template_id', 'first_name', 'last_name', 'email', 'phone', 'lock_contact',
                 'line_ids.question_id', 'line_ids.locked', 'line_ids.value_text', 'line_ids.value_text_area',
                 'line_ids.value_number', 'line_ids.value_integer', 'line_ids.value_date',
                 'line_ids.value_datetime', 'line_ids.value_option_id', 'line_ids.value_option_ids',
                 'line_ids.value_boolean', 'line_ids.value_latitude', 'line_ids.value_longitude',
                 'line_ids.value_reference', 'line_ids.value_reference_ids')
    def _compute_url(self):
        Report = self.env['ir.actions.report']
        for wizard in self:
            template = wizard.template_id
            url = template._public_url_for(wizard._url_params()) if template else False
            wizard.url = url
            wizard.qr_code = False
            if url:
                try:
                    png = Report.barcode('QR', url, width=300, height=300, barLevel='M')
                    wizard.qr_code = base64.b64encode(png)
                except Exception as error:  # noqa: BLE001 - the link still works without its QR code
                    _logger.info('Public URL QR code failed: %s', error)

    def _url_params(self):
        """The query string parameters [(key, value)] for what is filled in."""
        self.ensure_one()
        params, locked = [], []
        for key in CONTACT_KEYS:
            value = (self[key] or '').strip()
            if value:
                params.append((key, value))
                if self.lock_contact:
                    locked.append(key)
        seen = set()
        for line in self.line_ids.sorted(lambda l: (l.question_id.sequence, l.question_id.id)):
            if not line.question_id or line.question_id.id in seen:
                continue
            value = line._param_value()
            if value is None:
                continue
            seen.add(line.question_id.id)
            key = question_key(line.question_id.id)
            params.append((key, value))
            if line.locked:
                locked.append(key)
        if any(line.question_type == 'datetime' for line in self.line_ids):
            # Datetimes in the link are in the builder's time zone.
            params.append((TZ_KEY, self.env.user.tz or 'UTC'))
        if locked:
            params.append((LOCK_KEY, ','.join(locked)))
        return params

    def action_open_url(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.url, 'target': 'new'}


class ChecklistPublicUrlWizardLine(models.TransientModel):
    _name = 'checklist.public.url.wizard.line'
    _description = 'Checklist Public URL Builder Answer'

    wizard_id = fields.Many2one('checklist.public.url.wizard', required=True, ondelete='cascade')
    # The view limits it to the template's questions a link can answer.
    question_id = fields.Many2one('checklist.question', string='Question', required=True, ondelete='cascade')
    question_type = fields.Selection(related='question_id.question_type')
    relation_model_id = fields.Many2one(related='question_id.relation_model_id')
    relation_domain = fields.Char(related='question_id.relation_domain')
    locked = fields.Boolean(
        string='Lock', help='Shown read-only on the form: the person filling it in cannot change it.',
    )

    value_text = fields.Char(string='Text')
    value_text_area = fields.Text(string='Text Area')
    value_number = fields.Float(string='Number')
    value_integer = fields.Integer(string='Integer')
    value_date = fields.Date(string='Date')
    value_datetime = fields.Datetime(string='Datetime')
    value_option_id = fields.Many2one(
        'checklist.question.option', string='Answer', domain="[('question_id', '=', question_id)]",
    )
    value_option_ids = fields.Many2many(
        'checklist.question.option', 'checklist_public_url_line_option_rel', 'line_id', 'option_id',
        string='Answers', domain="[('question_id', '=', question_id)]",
    )
    value_boolean = fields.Boolean(string='Yes / No')
    value_latitude = fields.Float(string='Latitude', digits=(10, 7))
    value_longitude = fields.Float(string='Longitude', digits=(10, 7))
    value_reference = fields.Reference(selection='_selection_reference_models', string='Record')
    value_reference_ids = fields.Json(string='Records')
    value_display = fields.Char(string='Value', compute='_compute_value_display')

    @api.model
    def _selection_reference_models(self):
        return self.env['checklist.line']._selection_reference_models()

    @api.onchange('question_id')
    def _onchange_question_id(self):
        self.update({
            'value_text': False, 'value_text_area': False, 'value_number': 0, 'value_integer': 0,
            'value_date': False, 'value_datetime': False, 'value_option_id': False,
            'value_option_ids': [fields.Command.clear()], 'value_boolean': False,
            'value_latitude': 0, 'value_longitude': 0, 'value_reference': False, 'value_reference_ids': False,
        })

    @api.depends('question_id', 'value_text', 'value_text_area', 'value_number', 'value_integer',
                 'value_date', 'value_datetime', 'value_option_id', 'value_option_ids', 'value_boolean',
                 'value_latitude', 'value_longitude', 'value_reference', 'value_reference_ids')
    def _compute_value_display(self):
        for line in self:
            kind = line.question_type
            if kind in SINGLE_OPTION_TYPES:
                line.value_display = line.value_option_id.name or ''
            elif kind in MULTI_OPTION_TYPES:
                line.value_display = ', '.join(line.value_option_ids.mapped('name'))
            elif kind == 'boolean':
                line.value_display = self.env._('Yes') if line.value_boolean else self.env._('No')
            elif kind == 'many2one':
                line.value_display = line.value_reference.display_name if line.value_reference else ''
            elif kind == 'many2many':
                records = line._reference_records()
                line.value_display = ', '.join(records.mapped('display_name')) if records else ''
            else:
                line.value_display = line._param_value() or ''

    def _reference_records(self):
        self.ensure_one()
        model = self.relation_model_id.model
        ids = [i for i in self.value_reference_ids or [] if isinstance(i, int)]
        if not model or model not in self.env or not ids:
            return None
        return self.env[model].browse(ids).exists()

    def _param_value(self):
        """The answer as the link carries it, or None when there is none."""
        self.ensure_one()
        kind = self.question_type
        if not kind or kind in NOT_PREFILLABLE_TYPES:
            return None
        if kind in ('text', 'phone', 'email', 'website'):
            return (self.value_text or '').strip() or None
        if kind == 'text_area':
            return (self.value_text_area or '').strip() or None
        if kind == 'number':
            return ('%.6f' % self.value_number).rstrip('0').rstrip('.')
        if kind == 'integer':
            return str(self.value_integer)
        if kind == 'date':
            return self.value_date.strftime('%d/%m/%Y') if self.value_date else None
        if kind == 'datetime':
            if not self.value_datetime:
                return None
            return fields.Datetime.context_timestamp(self, self.value_datetime).strftime('%d/%m/%Y %H:%M')
        if kind in SINGLE_OPTION_TYPES:
            return str(self.value_option_id.id) if self.value_option_id else None
        if kind in MULTI_OPTION_TYPES:
            return ','.join(map(str, self.value_option_ids.ids)) or None
        if kind == 'boolean':
            return '1' if self.value_boolean else '0'
        if kind == 'geolocation':
            if not (self.value_latitude or self.value_longitude):
                return None
            return '%.7f,%.7f' % (self.value_latitude, self.value_longitude)
        if kind == 'many2one':
            return str(self.value_reference.id) if self.value_reference else None
        if kind == 'many2many':
            ids = [i for i in self.value_reference_ids or [] if isinstance(i, int)]
            return ','.join(map(str, ids)) or None
        return None

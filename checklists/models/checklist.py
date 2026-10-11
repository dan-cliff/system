# -*- coding: utf-8 -*-
import logging

import requests

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError

from .checklist_question_condition import (
    MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES, combine, eval_domain, evaluate_rule,
)
from .checklist_template import (
    COLUMN_COUNTS, COLUMNS, LAYOUT_TYPES, QUESTION_TYPES, TITLE_POSITIONS, group_panel_range,
)

_logger = logging.getLogger(__name__)


class Checklist(models.Model):
    _name = 'checklist.checklist'
    _description = 'Checklist'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'checklist_date desc, id desc'
    # With org_structure: the Company field heads the Organisation section.
    _org_form_company = True

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True, default='New',
    )
    template_id = fields.Many2one(
        'checklist.template', string='Template', required=True, tracking=True,
        ondelete='restrict', default=lambda self: self._default_template(),
    )
    # Stored so the side panel can count checklists per group; follows the
    # template's groups.
    group_ids = fields.Many2many(
        related='template_id.group_ids', string='Checklist Groups', store=True,
        relation='checklist_checklist_group_rel', column1='checklist_id', column2='group_id',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, tracking=True,
        default=lambda self: self.env.company,
    )
    checklist_date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today, tracking=True,
    )
    date_due = fields.Date(string='Due Date', tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Completed By', required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    # Technical workflow state, so a fixed selection.
    state = fields.Selection(
        [('draft', 'In Progress'), ('done', 'Completed')],
        string='Status', default='draft', required=True, tracking=True, copy=False,
    )
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    line_ids = fields.One2many(
        'checklist.line', 'checklist_id', string='Checks', copy=True,
    )
    notes = fields.Html(string='Notes')
    # Copied from the template, so past checklists keep their layout.
    column_count = fields.Selection(COLUMN_COUNTS, string='Layout', default='1')

    @api.model
    def _default_template(self):
        template_id = self.env['ir.config_parameter'].sudo().get_param('checklists.default_template_id')
        template = self.env['checklist.template'].browse(int(template_id or 0)).exists()
        return template if template.active else self.env['checklist.template']

    @api.depends('date_due', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for checklist in self:
            checklist.is_overdue = bool(
                checklist.state == 'draft' and checklist.date_due and checklist.date_due < today
            )

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(self.env._('Unsupported search on Overdue.'))
        domain = [('state', '=', 'draft'), ('date_due', '<', fields.Date.context_today(self))]
        return domain if (operator == '=') == value else ['!', '&'] + domain

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        if field_name == 'group_ids':
            return group_panel_range(self, field_name, **kwargs)
        return super().search_panel_select_range(field_name, **kwargs)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('checklist.checklist') or 'New'
            if vals.get('template_id'):
                template = self.env['checklist.template'].browse(vals['template_id'])
                vals.setdefault('column_count', template.column_count)
                if not vals.get('line_ids'):
                    vals['line_ids'] = self._template_line_commands(template)
        return super().create(vals_list)

    @api.model
    def _template_line_commands(self, template):
        return [Command.create(question._checklist_line_vals()) for question in template.question_ids]

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.state == 'draft':
            self.column_count = self.template_id.column_count or '1'
            self.line_ids = [Command.clear()] + self._template_line_commands(self.template_id)

    def action_complete(self):
        self.write({'state': 'done'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def write(self, vals):
        if 'template_id' in vals and any(rec.state == 'done' for rec in self):
            raise UserError(self.env._('The template of a completed checklist cannot be changed.'))
        return super().write(vals)


class ChecklistLine(models.Model):
    _name = 'checklist.line'
    _description = 'Checklist Check'
    _order = 'checklist_id, sequence, id'

    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist', required=True, ondelete='cascade', index=True,
    )
    state = fields.Selection(related='checklist_id.state')
    # The question is copied onto the line so later template edits don't
    # change what past checklists asked.
    question_id = fields.Many2one('checklist.question', string='Template Question', ondelete='set null')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Question', required=True)
    description = fields.Text(string='Description')
    question_type = fields.Selection(QUESTION_TYPES, string='Type', required=True, default='text')
    column = fields.Selection(COLUMNS, string='Column', default='1')

    value_text = fields.Char(string='Text')
    value_text_area = fields.Text(string='Text Area')
    value_number = fields.Float(string='Number')
    value_integer = fields.Integer(string='Integer')
    value_date = fields.Date(string='Date')
    value_datetime = fields.Datetime(string='Datetime')
    value_option_id = fields.Many2one(
        'checklist.question.option', string='Answer', ondelete='restrict',
        domain="[('question_id', '=', question_id)]",
    )
    value_option_ids = fields.Many2many(
        'checklist.question.option', 'checklist_line_option_rel', 'line_id', 'option_id',
        string='Answers', domain="[('question_id', '=', question_id)]",
    )
    value_boolean = fields.Boolean(string='Yes / No')
    value_latitude = fields.Float(string='Latitude', digits=(10, 7))
    value_longitude = fields.Float(string='Longitude', digits=(10, 7))
    value_address = fields.Char(string='Street Address')
    # GeoLocation display options, copied from the question.
    geo_show_coordinates = fields.Boolean(string='Show Latitude / Longitude', default=True)
    geo_show_map = fields.Boolean(string='Show Map')
    geo_show_address = fields.Boolean(string='Show Street Address')
    value_image = fields.Image(string='Image', max_width=1920, max_height=1920)
    value_file = fields.Binary(string='File', attachment=True)
    value_file_name = fields.Char(string='File Name')
    value_phone = fields.Char(string='Phone')
    # Phone Number buttons, copied from the question.
    phone_show_call = fields.Boolean(string='Show Call Button', default=True)
    phone_show_sms = fields.Boolean(string='Show SMS Button')
    # Email button, copied from the question.
    email_show_button = fields.Boolean(string='Show Email Button', default=True)
    # Website button, copied from the question.
    url_show_button = fields.Boolean(string='Show Open Link Button', default=True)
    value_email = fields.Char(string='Email')
    value_url = fields.Char(string='Website')
    # Many2one / Many2Many: copied from the question, like its title.
    relation_model_id = fields.Many2one('ir.model', string='Model', ondelete='set null')
    relation_domain = fields.Char(string='Filter', default='[]')
    value_reference = fields.Reference(selection='_selection_reference_models', string='Record')
    # Many2Many answers: ids of relation_model_id records.
    value_reference_ids = fields.Json(string='Records')

    # Section Title / Section Break / Instructions, copied from the question.
    layout_text_color = fields.Char(string='Text Colour')
    layout_bg_color = fields.Char(string='Background Colour')
    layout_border_color = fields.Char(string='Border Colour')
    layout_line_color = fields.Char(string='Line Colour')
    layout_title_position = fields.Selection(TITLE_POSITIONS, string='Title')
    instructions = fields.Html(string='Instructions', sanitize=True)

    # Conditional display, copied from the question (see checklist_question_condition.py).
    conditional = fields.Boolean(string='Conditional Display')
    condition_logic = fields.Selection([('all', 'All'), ('any', 'Any')], default='all')
    # [{question_id (template question), question_type, operator, value, option_ids}]
    condition_rules = fields.Json(string='Answer Conditions')
    condition_user_domain = fields.Char(default='[]')
    condition_record_domain = fields.Char(default='[]')
    # {'user': bool, 'record': bool} for the filters set (evaluated here, as
    # the form can't); the answer rules are evaluated live on the form.
    condition_context = fields.Json(compute='_compute_condition_context')

    @api.depends('conditional', 'condition_user_domain', 'condition_record_domain',
                 'checklist_id.company_id', 'checklist_id.template_id', 'checklist_id.user_id')
    @api.depends_context('uid')
    def _compute_condition_context(self):
        for line in self:
            result = {}
            if line.conditional:
                user_domain = eval_domain(self.env, line.condition_user_domain)
                if user_domain:
                    result['user'] = bool(self.env.user.sudo().filtered_domain(user_domain))
                record_domain = eval_domain(self.env, line.condition_record_domain)
                if record_domain:
                    result['record'] = bool(line.checklist_id.sudo().filtered_domain(record_domain))
            line.condition_context = result

    def _condition_answer(self):
        """The answer in the form the condition rules compare."""
        self.ensure_one()
        kind = self.question_type
        if kind in SINGLE_OPTION_TYPES:
            return self.value_option_id.id or False
        if kind in MULTI_OPTION_TYPES:
            return self.value_option_ids.ids
        if kind == 'many2many':
            return self.value_reference_ids or []
        if kind == 'many2one':
            return self.value_reference.id if self.value_reference else False
        if kind == 'geolocation':
            return bool(self.value_latitude or self.value_longitude)
        return {
            'text': self.value_text, 'text_area': self.value_text_area,
            'number': self.value_number, 'integer': self.value_integer,
            'date': self.value_date,
            'datetime': self.value_datetime and fields.Datetime.context_timestamp(self, self.value_datetime).date(),
            'boolean': self.value_boolean, 'image': bool(self.value_image), 'file': bool(self.value_file),
            'phone': self.value_phone, 'email': self.value_email, 'website': self.value_url,
        }.get(kind, False)

    def _is_visible(self, _seen=None):
        """Whether this line shows, given its conditions (used by the PDF)."""
        self.ensure_one()
        if not self.conditional:
            return True
        seen = (_seen or set()) | {self.id}
        answers = {line.question_id.id: line for line in self.checklist_id.line_ids if line.question_id}
        results = []
        for rule in self.condition_rules or []:
            source = answers.get(rule.get('question_id'))
            # A condition on a question that is itself hidden is not met.
            results.append(
                bool(source) and source.id not in seen and source._is_visible(seen)
                and evaluate_rule(rule, source._condition_answer())
            )
        context = self.condition_context or {}
        results += [context.get('user'), context.get('record')]
        return combine(self.condition_logic, results)

    @api.model
    def _selection_reference_models(self):
        return [(model.model, model.name) for model in self.env['ir.model'].sudo().search(
            [('transient', '=', False), ('abstract', '=', False)])]

    def _reference_records(self):
        """The records a Many2Many answer picked (that still exist)."""
        self.ensure_one()
        model = self.relation_model_id.model
        if not model or model not in self.env or not self.value_reference_ids:
            return None
        return self.env[model].browse([i for i in self.value_reference_ids if isinstance(i, int)]).exists()

    def _answer_display(self):
        """The answer as text, for reports (dates as dd/mm/yyyy)."""
        self.ensure_one()
        kind = self.question_type
        if kind in LAYOUT_TYPES:
            return ''
        if kind == 'text':
            return self.value_text or ''
        if kind == 'text_area':
            return self.value_text_area or ''
        if kind == 'number':
            return ('%.2f' % self.value_number).rstrip('0').rstrip('.')
        if kind == 'integer':
            return str(self.value_integer)
        if kind == 'date':
            return self.value_date.strftime('%d/%m/%Y') if self.value_date else ''
        if kind == 'datetime':
            if not self.value_datetime:
                return ''
            return fields.Datetime.context_timestamp(self, self.value_datetime).strftime('%d/%m/%Y %H:%M')
        if kind in ('buttons', 'select', 'radio', 'slider'):
            return self.value_option_id.name or ''
        if kind in ('multi_select', 'multi_checkbox'):
            return ', '.join(self.value_option_ids.mapped('name'))
        if kind == 'boolean':
            return self.env._('Yes') if self.value_boolean else self.env._('No')
        if kind == 'geolocation':
            if not (self.value_latitude or self.value_longitude):
                return ''
            coordinates = '%.6f, %.6f' % (self.value_latitude, self.value_longitude)
            address = self.geo_show_address and self.value_address
            if address and not self.geo_show_coordinates:
                return address
            return '%s\n%s' % (address, coordinates) if address else coordinates
        if kind == 'file':
            return self.value_file_name or (self.env._('File attached') if self.value_file else '')
        if kind == 'phone':
            return self.value_phone or ''
        if kind == 'email':
            return self.value_email or ''
        if kind == 'website':
            return self.value_url or ''
        try:
            if kind == 'many2one':
                return self.value_reference.display_name if self.value_reference else ''
            if kind == 'many2many':
                records = self._reference_records()
                return ', '.join(records.mapped('display_name')) if records else ''
        except AccessError:
            return self.env._('(no access)')
        return ''

    @api.onchange('value_phone')
    def _onchange_value_phone(self):
        # Odoo's phone formatting (phone_validation), for the user's country.
        if self.value_phone and self.question_type == 'phone':
            country = (self.env.user.country_id or self.checklist_id.company_id.country_id
                       or self.env.company.country_id)
            formatted = self._phone_format_number(self.value_phone, country, force_format='INTERNATIONAL')
            if formatted:
                self.value_phone = formatted

    @api.model
    def checklist_reverse_geocode(self, latitude, longitude):
        """The closest street address to a location (OpenStreetMap Nominatim),
        or False when it can't be found."""
        try:
            response = requests.get(
                'https://nominatim.openstreetmap.org/reverse',
                params={'format': 'jsonv2', 'lat': float(latitude), 'lon': float(longitude),
                        'accept-language': self.env.lang or 'en'},
                headers={'User-Agent': 'Odoo Checklists (%s)' % self.env.company.name},
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get('display_name') or False
        except (requests.RequestException, ValueError, TypeError) as error:
            _logger.info('Street address lookup failed: %s', error)
            return False

    def _answer_badge_style(self):
        """Inline style colouring a Buttons answer like its button, or ''."""
        self.ensure_one()
        colour = self.question_type in ('buttons', 'select', 'radio', 'slider') and self.value_option_id.color
        if not colour:
            return ''
        hex_colour = colour.lstrip('#')
        try:
            r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return ''
        text = '#000' if 0.299 * r + 0.587 * g + 0.114 * b > 160 else '#fff'
        return f'background-color: {colour}; color: {text};'

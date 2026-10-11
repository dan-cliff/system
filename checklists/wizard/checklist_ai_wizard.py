# -*- coding: utf-8 -*-
"""AI Template Generator: a checklist template written by AI from a prompt.

Uses the API keys on Settings › General Settings › Integrations (AI
Integration Settings): Claude first, Google Gemini if Claude isn't set up or
fails. The AI answers with a template in the JSON export layout, which is
then imported like a template file.
"""
import json
import logging
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.checklist_template import LAYOUT_TYPES, OPTION_TYPES

_logger = logging.getLogger(__name__)

CLAUDE_MODEL = 'claude-opus-5-5'
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

# Question types the AI may use (Many2one / Many2Many need a model chosen by hand).
AI_QUESTION_TYPES = [
    'buttons', 'select', 'radio', 'multi_select', 'multi_checkbox', 'slider',
    'text', 'text_area', 'number', 'integer', 'date', 'datetime', 'boolean',
    'geolocation', 'image', 'file', 'phone', 'email', 'website',
    'section_title', 'section_break', 'instructions',
]
HEX_COLOUR = re.compile(r'^#[0-9a-fA-F]{6}$')

TEMPLATE_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': {'type': 'string'},
        'description': {'type': 'string'},
        'columns': {'type': 'string', 'enum': ['1', '2', '3']},
        'asset_label': {'type': 'string'},
        'questions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'description': {'type': 'string'},
                    'question_type': {'type': 'string', 'enum': AI_QUESTION_TYPES},
                    'column': {'type': 'string', 'enum': ['1', '2', '3']},
                    'options': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'},
                                'color': {'type': 'string'},
                            },
                            'required': ['name', 'color'],
                            'additionalProperties': False,
                        },
                    },
                    'instructions_html': {'type': 'string'},
                    'text_color': {'type': 'string'},
                    'background_color': {'type': 'string'},
                    'border_color': {'type': 'string'},
                    'line_color': {'type': 'string'},
                },
                'required': [
                    'name', 'description', 'question_type', 'column', 'options',
                    'instructions_html', 'text_color', 'background_color', 'border_color', 'line_color',
                ],
                'additionalProperties': False,
            },
        },
    },
    'required': ['name', 'description', 'columns', 'asset_label', 'questions'],
    'additionalProperties': False,
}

SYSTEM_PROMPT = """You design checklist templates for an Odoo Checklists app. People fill \
these checklists in on phones, tablets and desktops, so make them practical: clear, \
specific questions in the order someone would work through the task, grouped into sections.

Question types:
- buttons: the person taps one of the options (best for pass/fail style checks, e.g. \
"Pass" #198754, "Fail" #dc3545, "N/A" #6c757d). Give every option a colour.
- select: one option from a dropdown (long lists). radio: one option from a short list. \
slider: one option along a scale (e.g. Poor → Excellent). multi_select / multi_checkbox: \
several options. These all need options.
- text (short answer), text_area (notes), number, integer, date, datetime, boolean (yes/no toggle).
- geolocation (where it was done), image (photo evidence), file (an attachment), phone, \
email, website.
- section_title: a heading box for a section, with the description as a subtitle. \
Use text/background/border colours that read well together.
- section_break: a dividing line (line colour), titled with the next part's name.
- instructions: formatted guidance shown on the form, written as simple HTML in \
instructions_html (<p>, <ul>/<ol>/<li>, <strong>). Use it for safety notes or steps.

Rules:
- Start sections with a section_title; keep each section focused.
- Use options only for buttons, select, radio, slider, multi_select and multi_checkbox; \
leave options empty for every other type.
- Colours are hex like #1d4ed8, or an empty string when they don't apply.
- columns: "1" for most checklists; "2" or "3" only for short, form-like checklists. \
Every question's column must not exceed columns (use "1" when columns is "1").
- Fill unused text fields with an empty string.
- asset_label: when the checklist is for an asset, a short name for it (e.g. "Vehicle", \
"Forklift", "First Aid Kit"); otherwise an empty string.
- Use Australian English."""


class ChecklistAiWizard(models.TransientModel):
    _name = 'checklist.ai.wizard'
    _description = 'AI Checklist Template Generator'

    prompt = fields.Text(
        string='What should the checklist cover?', required=True,
        help='Describe the checklist: what is being checked, by whom and anything it must include.',
    )
    group_ids = fields.Many2many(
        'checklist.group', 'checklist_ai_wizard_group_rel', 'wizard_id', 'group_id',
        string='Checklist Groups',
    )
    asset_enabled = fields.Boolean(
        string='Asset Enabled',
        help='Checklists from the template record the asset they are for (Asset Management).',
    )
    asset_available = fields.Boolean(compute='_compute_asset_available')
    provider = fields.Char(compute='_compute_provider', string='AI Provider')

    def _compute_asset_available(self):
        available = 'asset_enabled' in self.env['checklist.template']._fields
        for wizard in self:
            wizard.asset_available = available

    def _compute_provider(self):
        names = [label for _key, label, _model in self._providers()]
        for wizard in self:
            wizard.provider = ', then '.join(names) if names else False

    # ── Providers ────────────────────────────────────────────────────────

    @api.model
    def _providers(self):
        """[(api key, label, method)] in the order to try them: Claude first."""
        params = self.env['ir.config_parameter'].sudo()
        providers = []
        claude_key = params.get_param('claude_ai_settings.api_key')
        if claude_key:
            providers.append((claude_key, 'Claude', self._generate_claude))
        gemini_key = params.get_param('claude_ai_settings.gemini_api_key')
        if gemini_key:
            providers.append((gemini_key, 'Google Gemini', self._generate_gemini))
        return providers

    def _user_prompt(self):
        self.ensure_one()
        lines = ['Create a checklist template for this request:', self.prompt.strip()]
        if self.group_ids:
            lines.append('It belongs to these Checklist Groups: %s.' % ', '.join(self.group_ids.mapped('name')))
        if self.asset_enabled and self.asset_available:
            lines.append('Each checklist is filled in for one asset (e.g. a vehicle or a piece of '
                         'equipment), chosen on the checklist: set asset_label.')
        return '\n\n'.join(lines)

    @api.model
    def _generate_claude(self, api_key, system, user_prompt):
        try:
            import anthropic
        except ImportError as error:
            raise UserError(self.env._(
                'The anthropic Python package is not installed on the server.')) from error
        client = anthropic.Anthropic(api_key=api_key, timeout=600.0, max_retries=2)
        try:
            # Streamed: a long template can take a while to write. The server-side
            # fallback re-runs the request on another model if this one declines.
            with client.beta.messages.stream(
                model=CLAUDE_MODEL,
                max_tokens=32000,
                betas=['server-side-fallback-2026-07-01'],
                fallbacks='default',
                output_config={
                    'effort': 'medium',
                    'format': {'type': 'json_schema', 'schema': TEMPLATE_SCHEMA},
                },
                system=system,
                messages=[{'role': 'user', 'content': user_prompt}],
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as error:
            raise UserError(self.env._('Claude rejected the API key.')) from error
        except anthropic.RateLimitError as error:
            raise UserError(self.env._('Claude is rate limited; try again shortly.')) from error
        except anthropic.APIStatusError as error:
            raise UserError(self.env._('Claude returned an error (%(status)s): %(message)s',
                                       status=error.status_code, message=error.message)) from error
        except anthropic.APIConnectionError as error:
            raise UserError(self.env._('Could not reach Claude: %s', error)) from error
        if message.stop_reason == 'refusal':
            raise UserError(self.env._('Claude declined to write this checklist.'))
        if message.stop_reason == 'max_tokens':
            raise UserError(self.env._('The checklist was too long to finish; try a narrower request.'))
        text = next((block.text for block in message.content if block.type == 'text'), '')
        return json.loads(text)

    @api.model
    def _generate_gemini(self, api_key, system, user_prompt):
        try:
            response = requests.post(
                GEMINI_URL % GEMINI_MODEL,
                params={'key': api_key},
                json={
                    'system_instruction': {'parts': [{'text': system + '\n\nReply with only a JSON object '
                                                      'matching this JSON schema:\n' + json.dumps(TEMPLATE_SCHEMA)}]},
                    'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
                    'generationConfig': {'responseMimeType': 'application/json', 'maxOutputTokens': 32768},
                },
                timeout=300,
            )
            response.raise_for_status()
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.HTTPError as error:
            raise UserError(self.env._('Google Gemini returned an error (%s).', error.response.status_code)) from error
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            raise UserError(self.env._('Could not get an answer from Google Gemini: %s', error)) from error
        return json.loads(text)

    # ── Generation ───────────────────────────────────────────────────────

    def action_generate(self):
        """Write the template with AI and open it."""
        self.ensure_one()
        if not (self.prompt or '').strip():
            raise UserError(self.env._('Describe the checklist you want.'))
        providers = self._providers()
        if not providers:
            raise UserError(self.env._(
                'No AI is set up. Add a Claude AI or Google Gemini API key in Settings › '
                'General Settings › Integrations.'))
        errors = []
        for api_key, label, generate in providers:
            try:
                answer = generate(api_key, SYSTEM_PROMPT, self._user_prompt())
                template_data = self._template_data(answer)
                break
            except (UserError, ValueError, TypeError, KeyError) as error:
                _logger.warning('AI Template Generator: %s failed: %s', label, error)
                errors.append('%s: %s' % (label, error))
        else:
            raise UserError(self.env._('The checklist could not be generated.\n\n%s', '\n'.join(errors)))
        Templates = self.env['checklist.template']
        Templates._validate_templates_data([template_data])
        template = Templates._import_templates_data([template_data])
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'checklist.template',
            'res_id': template.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _template_data(self, answer):
        """The AI's answer as a template in the JSON export layout, tidied."""
        self.ensure_one()
        if not isinstance(answer, dict) or not answer.get('questions'):
            raise ValueError('the answer has no questions')
        columns = answer.get('columns') if answer.get('columns') in ('1', '2', '3') else '1'
        colour = lambda value: value if isinstance(value, str) and HEX_COLOUR.match(value) else ''
        questions = []
        for index, item in enumerate(answer['questions']):
            kind = item.get('question_type')
            if kind not in AI_QUESTION_TYPES or not (item.get('name') or '').strip():
                continue
            column = item.get('column') if item.get('column') in ('1', '2', '3') else '1'
            layout = {
                'layout_text_color': colour(item.get('text_color')),
                'layout_bg_color': colour(item.get('background_color')),
                'layout_border_color': colour(item.get('border_color')),
                'layout_line_color': colour(item.get('line_color')),
                'instructions': (item.get('instructions_html') or '') if kind == 'instructions' else '',
            }
            questions.append({
                'name': item['name'].strip()[:200],
                'description': (item.get('description') or '').strip(),
                'question_type': kind,
                'sequence': (index + 1) * 10,
                'column': min(column, columns),
                'layout': {key: value for key, value in layout.items() if value},
                'options': [
                    {'name': option['name'].strip(), 'sequence': (i + 1) * 10,
                     'color': colour(option.get('color'))}
                    for i, option in enumerate(item.get('options') or [])
                    if kind in OPTION_TYPES and (option.get('name') or '').strip()
                ],
            })
        if not any(q['question_type'] not in LAYOUT_TYPES for q in questions):
            raise ValueError('the answer has no usable questions')
        data = {
            'name': (answer.get('name') or 'AI Checklist').strip()[:200],
            'description': (answer.get('description') or '').strip(),
            'columns': columns,
            'group_ids': self.group_ids.ids,
            'questions': questions,
        }
        if self.asset_enabled and self.asset_available:
            data['asset'] = {
                'enabled': True, 'required': False, 'filter': '[]',
                'label': (answer.get('asset_label') or '').strip()[:60],
            }
        return data

"""Author dashboards from a plain-language request with Claude or Gemini.

The browser asks for the available engines (``ai_get_providers``) and then
calls ``ai_generate`` once per engine, Claude first, until one succeeds. One
engine per request keeps each call inside Odoo's request time limit.

Each engine gets two steps:

1. pick the models (data sources) the request needs from the models the
   user can read;
2. design the dashboard from the widget library, the fields of those
   models and the gridstack.js layout rules.

The answer is validated against the database before anything is created:
unknown models, fields or options are dropped, and a widget whose data still
fails to load is removed, so the new dashboard always opens cleanly.
"""
import json
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .dashboard import MANAGER_GROUP
from .dashboard_widget import (
    AGGREGATES, AXIS_SORTS, DATE_TYPES, ELAPSED_UNITS, GROUPABLE_TYPES, INTERVALS, MAP_LEVELS,
    MEASURE_TYPES, SORTS, USER_FILTER_MODELS, USER_SCOPES, VALUE_MODES,
)

_logger = logging.getLogger(__name__)

# Keys entered in Settings > General Settings (claude_ai_settings module).
CLAUDE_KEY_PARAM = 'claude_ai_settings.api_key'
GEMINI_KEY_PARAM = 'claude_ai_settings.gemini_api_key'
# Optional overrides, as system parameters.
CLAUDE_MODEL_PARAM = 'custom_dashboard.ai_claude_model'
GEMINI_MODEL_PARAM = 'custom_dashboard.ai_gemini_model'
CLAUDE_MODEL = 'claude-opus-5-5'
CLAUDE_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_HEADERS = {
    'anthropic-version': '2023-06-01',
    # fallbacks="default": a declined request is retried on Anthropic's
    # recommended fallback model inside the same call.
    'anthropic-beta': 'server-side-fallback-2026-07-01',
    'content-type': 'application/json',
}
GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-flash-latest']
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'
# Seconds per AI call. Two calls must fit in one Odoo request (120 s by default).
AI_TIMEOUT = 50
PROVIDERS = [
    ('claude', 'Claude AI', CLAUDE_KEY_PARAM),
    ('gemini', 'Google Gemini', GEMINI_KEY_PARAM),
]

MAX_PROMPT = 4000
MAX_MODELS = 6
MAX_FIELDS = 150
MAX_WIDGETS = 24
MAX_SELECTION = 25
COLUMNS = 12
# Technical models no dashboard needs, kept out of the catalogue.
SKIPPED_PREFIXES = (
    'ir.', 'base.', 'bus.', 'res.config', 'web_', 'web.', 'auth_', 'iap.', 'digest.', 'mail.alias',
    'mail.followers', 'mail.notification', 'mail.tracking', 'mail.mail', 'mail.template', 'spreadsheet.',
    'report.', 'custom.dashboard', 'rpc.', 'html_field', 'onboarding.', 'privacy.', 'sms.tracker',
    'fetchmail.', 'snailmail.', 'barcode', 'format.address', 'avatar.', 'image.mixin', 'website.seo',
)
HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

SYSTEM_PROMPT = """You design dashboards for Odoo 19, an ERP system, inside a \
custom dashboard app. You get a user's request plus a description of the data \
the user can read, and you answer with JSON only. Use only the models, fields \
and options listed; anything else is discarded. Write every name, description, \
title, subtitle, label and text in {language}, whatever language the request or \
the field labels are in. Show dates as dd/mm/yyyy in any text you write."""

PICK_MODELS_PROMPT = """A user wants this dashboard:

<request>
{request}
</request>

These are the Odoo models (data sources) the user can read, as \
"technical_name: label":

<models>
{catalogue}
</models>

Choose the models whose records the dashboard needs, most important first, at \
most {max_models}. Prefer the main business document (for example sale.order \
over sale.order.line) unless the request needs line-level detail. Answer with \
JSON: {{"models": ["technical.name", ...]}}"""

DESIGN_PROMPT = """A user wants this dashboard:

<request>
{request}
</request>

Design it. Today is {today}. The user's company is {company} and its currency \
symbol is "{currency}".

## Layout: gridstack.js

The dashboard is a gridstack.js grid, 12 columns wide. Each widget has a \
position and size in grid cells: x (column, 0-11), y (row, 0 is the top), w \
(width in columns, 1-12) and h (height in rows; one row is 80 px). x + w must \
not exceed 12 and widgets must not overlap. Lay the dashboard out like a \
professional business-intelligence report:
- a row of KPI or gauge cards across the top (for example four cards of w=3, \
h=2, or three of w=4, h=2);
- the main charts below, usually two side by side (w=6, h=4 or h=5) or a wide \
trend (w=12 or w=8, h=4);
- detail tables and pivots towards the bottom (w=6-12, h=5-7);
- pie and donut charts work best at w=4-6, h=4; maps at w=6-12, h=5-7;
- fill every row edge to edge (widths in a row add up to 12) and leave no gaps;
- a text widget (w=12, h=1 or 2) can introduce the dashboard or a section.
Aim for 5 to 12 widgets unless the request asks for something else.

## Widget library

Every widget has a "type" (the code below). How it gets its data depends on \
its data mode:
- grouped: records grouped by "group_by" (a groupable field), optionally \
split into series by "series", with "measure" aggregated by "aggregate" for \
each group (no measure = count of records). Date and datetime group-bys use \
"group_by_interval" (and "series_interval" for a date series).
- single: one number. "value_mode" "aggregate" aggregates "measure" (or counts \
records); "value_mode" "elapsed" shows the time since the latest date in \
"elapsed_field", counted in "elapsed_unit".
- points: one dot per record (up to the limit); "measure" is the X axis and \
"measure2" the Y axis; bubble size is the count of records at that spot.
- map: countries, states or contact locations shaded by "measure". \
"map_level" is country, state or point. "map_address_path" is a dotted path of \
many2one fields from the model to a contact (res.partner) whose address \
places each record (leave it null when the model is res.partner itself). \
"map_country_code" (ISO code such as "AU") focuses the map on one country.
- content: no data. "text" shows "text_content" (simple HTML); "image" needs \
an upload, so do not use it.

{widget_types}

## Widget options

Every widget: "type", "title" (short, e.g. "Revenue by Month"), "x", "y", "w", \
"h" are required. Optional:
- "subtitle": a short line under the title.
- "model": technical name of the data source (every type except text).
- "domain": an Odoo domain filter as a Python list string, e.g. \
"[('state', '=', 'sale')]". Only use fields from the field list below. Dates \
in domains can use context_today() and relativedelta, e.g. \
"[('date_order', '>=', context_today() - relativedelta(months=12))]". \
Use "[]" for no filter.
- "group_by", "series": field names; must be groupable (types {groupable}).
- "group_by_interval", "series_interval": {intervals}.
- "measure", "measure2": numeric field names (types {measures}); null counts \
records. Combo charts draw "measure" as columns and "measure2" as a line.
- "aggregate", "aggregate2": {aggregates}.
- "sort": {sorts} (not for pivot). "limit": show only the first N groups \
(0 = all); use it with value sorts for "top 10" style charts.
- Pivot only: "pivot_row_sort", "pivot_col_sort": {axis_sorts}; \
"pivot_show_all_rows", "pivot_show_all_columns": true to list every option of \
the field even without records; "pivot_row_label", "pivot_col_label": axis \
captions; "pivot_hide_none_rows", "pivot_hide_none_columns", \
"pivot_hide_row_totals", "pivot_hide_column_totals": booleans.
- "value_mode": {value_modes}; "elapsed_field": a date or datetime field; \
"elapsed_unit": {elapsed_units}.
- "map_level": {map_levels}; "map_address_path"; "map_country_code".
- "user_filter_scope": {user_scopes} - limits records to the person viewing \
the dashboard ("self"), their manager, their team (people they manage) or \
their extended team (themselves and everyone below them). \
"user_filter_path": dotted many2one path from the model to a res.users or \
hr.employee record (e.g. "user_id"); null when the model is res.users or \
hr.employee. Use it for "my ..." requests.
- "target": a goal value for KPI and gauge cards; "gauge_min", "gauge_max": \
the gauge range.
- "decimals", "prefix", "suffix": number formatting (e.g. prefix "{currency}" \
for money).
- "show_legend", "show_values", "show_border", "show_shadow": booleans.
- "colors": up to 6 hex colours ("#1f77b4"); charts cycle through them. Leave \
it out to use the company's default colours.
- "text_content": HTML for text widgets (h3, p, ul, b, i only).

## Data the user can read

Fields are listed as "name (type, label)"; many2one fields name the model they \
point to, and selection fields list their values.

{fields}

Write the dashboard name, description and every widget's text in {language}.
Answer with JSON only, in this shape:
{{"name": "Dashboard name", "description": "One sentence", "widgets": [{{"type": "kpi", \
"title": "...", "x": 0, "y": 0, "w": 3, "h": 2, "model": "...", ...}}]}}"""


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


class CustomDashboard(models.Model):
    _inherit = 'custom.dashboard'

    # ------------------------------------------------------------------
    # Front-end API
    # ------------------------------------------------------------------
    @api.model
    def ai_get_providers(self):
        """Engines with an API key, in the order to try them. Empty when the
        user cannot build dashboards, which hides the button."""
        if not self.env.user.has_group(MANAGER_GROUP):
            return []
        params = self.env['ir.config_parameter'].sudo()
        return [
            {'code': code, 'name': name}
            for code, name, param in PROVIDERS
            if (params.get_param(param) or '').strip()
        ]

    @api.model
    def ai_generate(self, prompt, provider):
        """Build a dashboard for ``prompt`` with one engine.

        Returns ``{"dashboard_id", "name", "provider", "warnings"}``. Raises
        UserError when the engine fails, so the browser can try the next one.
        """
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_('Only dashboard managers can generate dashboards.'))
        prompt = (prompt or '').strip()
        if not prompt:
            raise UserError(_('Describe the dashboard you want.'))
        prompt = prompt[:MAX_PROMPT]
        names = dict((code, name) for code, name, _param in PROVIDERS)
        if provider not in names:
            raise UserError(_('Unknown AI engine: %s', provider))
        key = (self.env['ir.config_parameter'].sudo().get_param(dict(
            (code, param) for code, _name, param in PROVIDERS)[provider]) or '').strip()
        if not key:
            raise UserError(_('No API key is set for %s.', names[provider]))

        catalogue = self._ai_model_catalogue()
        if not catalogue:
            raise UserError(_('You cannot read any data to build a dashboard from.'))
        picked = self._ai_ask(provider, key, PICK_MODELS_PROMPT.format(
            request=prompt,
            catalogue='\n'.join('%s: %s' % item for item in catalogue.items()),
            max_models=MAX_MODELS,
        ), self._ai_models_schema(), effort='low')
        model_names = [m for m in (picked.get('models') or []) if m in catalogue][:MAX_MODELS]
        if not model_names:
            raise UserError(_('%s did not find any data for this request.', names[provider]))

        design = self._ai_ask(provider, key, self._ai_design_prompt(prompt, model_names),
                              self._ai_design_schema(), effort='medium')
        dashboard, warnings = self._ai_create_dashboard(design, set(model_names), prompt)
        return {
            'dashboard_id': dashboard.id,
            'name': dashboard.name,
            'provider': names[provider],
            'warnings': warnings,
        }

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------
    @api.model
    def _ai_model_catalogue(self):
        """``{model: label}`` of the business models the user can read."""
        result = {}
        for record in self.env['ir.model'].sudo().search(
                [('transient', '=', False), ('abstract', '=', False)], order='model'):
            name = record.model
            if name.startswith(SKIPPED_PREFIXES) or name not in self.env:
                continue
            Model = self.env[name]
            if Model._abstract or Model._transient or not Model._auto:
                continue
            if not Model.has_access('read'):
                continue
            result[name] = record.name
        return result

    @api.model
    def _ai_field_lines(self, model_name):
        Model = self.env[model_name]
        lines = []
        # Stored fields first: those can be grouped, measured and filtered.
        for name, field in sorted(Model._fields.items(), key=lambda item: (not item[1].store, item[0])):
            if len(lines) >= MAX_FIELDS:
                break
            if name in models.MAGIC_COLUMNS and name not in ('create_date', 'create_uid'):
                continue
            if not field.store and field.type != 'many2one':
                continue
            if field.type not in GROUPABLE_TYPES + MEASURE_TYPES + ('many2many',):
                continue
            if field.groups and not self._ai_user_in_groups(field.groups):
                continue
            label = field.string or name
            if field.type in ('many2one', 'many2many'):
                info = '%s -> %s' % (field.type, field.comodel_name)
            else:
                info = field.type
            if not field.store:
                info += ', not stored: paths only'
            line = '- %s (%s, %s)' % (name, info, label)
            if field.type == 'selection':
                try:
                    values = field._description_selection(self.env)
                except Exception:  # noqa: BLE001 - selection callables vary
                    values = []
                if values:
                    line += ' values: ' + ', '.join(
                        '%s=%s' % (key, value) for key, value in values[:MAX_SELECTION])
            lines.append(line)
        return lines

    @api.model
    def _ai_user_in_groups(self, groups):
        return any(self.env.user.has_group(group.strip()) for group in groups.split(','))

    @api.model
    def _ai_widget_types(self):
        return self.env['custom.dashboard.widget.type'].search([])

    @api.model
    def _ai_design_prompt(self, prompt, model_names):
        types = self._ai_widget_types()
        type_lines = ['| type | name | data mode | series | second measure | default w x h | use for |',
                      '|---|---|---|---|---|---|---|']
        for t in types:
            if t.code == 'image':
                continue
            series = 'required' if t.requires_series else ('optional' if t.supports_series else 'no')
            type_lines.append('| %s | %s | %s | %s | %s | %sx%s | %s |' % (
                t.code, t.name, t.data_mode, series, 'yes' if t.uses_second_measure else 'no',
                t.default_width or 4, t.default_height or 4, t.description or '',
            ))
        field_blocks = []
        catalogue = self._ai_model_catalogue()
        for name in model_names:
            field_blocks.append('### %s (%s)\n%s' % (
                name, catalogue.get(name, name), '\n'.join(self._ai_field_lines(name))))
        company = self.env.company
        keys = lambda choices: ', '.join(key for key, _label in choices)  # noqa: E731
        return DESIGN_PROMPT.format(
            request=prompt,
            today=fields.Date.context_today(self).strftime('%d/%m/%Y'),
            company=company.name,
            currency=company.currency_id.symbol or '',
            widget_types='\n'.join(type_lines),
            groupable=', '.join(GROUPABLE_TYPES),
            measures=', '.join(MEASURE_TYPES),
            intervals=keys(INTERVALS),
            aggregates=keys(AGGREGATES),
            sorts=keys(SORTS),
            axis_sorts=keys(AXIS_SORTS),
            value_modes=keys(VALUE_MODES),
            elapsed_units=keys(ELAPSED_UNITS),
            map_levels=keys(MAP_LEVELS),
            user_scopes=keys(USER_SCOPES),
            fields='\n\n'.join(field_blocks),
            language=self._ai_language(),
        )

    @api.model
    def _ai_models_schema(self):
        return {
            'type': 'object',
            'properties': {'models': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['models'],
            'additionalProperties': False,
        }

    @api.model
    def _ai_design_schema(self):
        string, integer, number, boolean = (
            {'type': 'string'}, {'type': 'integer'}, {'type': 'number'}, {'type': 'boolean'})

        def enum(choices):
            return _nullable({'type': 'string', 'enum': [key for key, _label in choices]})

        codes = [t.code for t in self._ai_widget_types() if t.code != 'image']
        widget = {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'enum': codes},
                'title': string,
                'subtitle': _nullable(string),
                'x': integer, 'y': integer, 'w': integer, 'h': integer,
                'model': _nullable(string),
                'domain': _nullable(string),
                'group_by': _nullable(string),
                'group_by_interval': enum(INTERVALS),
                'series': _nullable(string),
                'series_interval': enum(INTERVALS),
                'measure': _nullable(string),
                'aggregate': enum(AGGREGATES),
                'measure2': _nullable(string),
                'aggregate2': enum(AGGREGATES),
                'sort': enum(SORTS),
                'limit': _nullable(integer),
                'pivot_row_sort': enum(AXIS_SORTS),
                'pivot_col_sort': enum(AXIS_SORTS),
                'pivot_show_all_rows': _nullable(boolean),
                'pivot_show_all_columns': _nullable(boolean),
                'pivot_row_label': _nullable(string),
                'pivot_col_label': _nullable(string),
                'pivot_hide_none_rows': _nullable(boolean),
                'pivot_hide_none_columns': _nullable(boolean),
                'pivot_hide_row_totals': _nullable(boolean),
                'pivot_hide_column_totals': _nullable(boolean),
                'value_mode': enum(VALUE_MODES),
                'elapsed_field': _nullable(string),
                'elapsed_unit': enum(ELAPSED_UNITS),
                'map_level': enum(MAP_LEVELS),
                'map_address_path': _nullable(string),
                'map_country_code': _nullable(string),
                'user_filter_scope': enum(USER_SCOPES),
                'user_filter_path': _nullable(string),
                'target': _nullable(number),
                'gauge_min': _nullable(number),
                'gauge_max': _nullable(number),
                'decimals': _nullable(integer),
                'prefix': _nullable(string),
                'suffix': _nullable(string),
                'show_legend': _nullable(boolean),
                'show_values': _nullable(boolean),
                'show_border': _nullable(boolean),
                'show_shadow': _nullable(boolean),
                'colors': _nullable({'type': 'array', 'items': string}),
                'text_content': _nullable(string),
            },
            'required': ['type', 'title', 'x', 'y', 'w', 'h'],
            'additionalProperties': False,
        }
        return {
            'type': 'object',
            'properties': {
                'name': string,
                'description': string,
                'widgets': {'type': 'array', 'items': widget},
            },
            'required': ['name', 'description', 'widgets'],
            'additionalProperties': False,
        }

    # ------------------------------------------------------------------
    # Engines
    # ------------------------------------------------------------------
    @api.model
    def _ai_language(self):
        """The language of the user's main company, e.g. "English (AU)"."""
        company = self.env.user.company_id
        code = company.partner_id.lang or self.env.user.lang or 'en_US'
        lang = self.env['res.lang']._lang_get(code)
        name = lang.name if lang else code
        if company.country_id:
            name = '%s, as written in %s' % (name, company.country_id.name)
        return name

    @api.model
    def _ai_system_prompt(self):
        return SYSTEM_PROMPT.format(language=self._ai_language())

    @api.model
    def _ai_ask(self, provider, key, prompt, schema, effort='medium'):
        """Send ``prompt`` to ``provider`` and return the parsed JSON answer."""
        system = self._ai_system_prompt()
        if provider == 'claude':
            text = self._ai_ask_claude(key, system, prompt, schema, effort)
        else:
            text = self._ai_ask_gemini(key, system, prompt, schema)
        return self._ai_parse_json(text)

    @api.model
    def _ai_ask_claude(self, key, system, prompt, schema, effort):
        """Call the Claude Messages API over HTTPS, with no extra Python
        package to install on the server."""
        model = self.env['ir.config_parameter'].sudo().get_param(CLAUDE_MODEL_PARAM) or CLAUDE_MODEL
        payload = {
            'model': model,
            'max_tokens': 16000,
            'fallbacks': 'default',
            'system': system,
            'messages': [{'role': 'user', 'content': prompt}],
            'output_config': {
                'effort': effort,
                'format': {'type': 'json_schema', 'schema': schema},
            },
        }
        headers = {**CLAUDE_HEADERS, 'x-api-key': key}
        try:
            response = requests.post(CLAUDE_URL, json=payload, timeout=(10, AI_TIMEOUT), headers=headers)
            if response.status_code == 400 and 'fallback' in response.text:
                # The refusal fallback is optional; never let it block the call.
                payload.pop('fallbacks')
                headers.pop('anthropic-beta')
                response = requests.post(CLAUDE_URL, json=payload, timeout=(10, AI_TIMEOUT), headers=headers)
        except requests.exceptions.Timeout as error:
            raise UserError(_('Claude AI took too long to answer. Try a smaller request.')) from error
        except requests.exceptions.RequestException as error:
            raise UserError(_('Could not reach Claude AI: %s', error)) from error
        if response.status_code == 401:
            raise UserError(_('Claude AI rejected the API key.'))
        if response.status_code == 429:
            raise UserError(_('Claude AI is busy (rate limited). Try again shortly.'))
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200:
            detail = (body.get('error') or {}).get('message') or response.text[:300]
            _logger.warning('Claude AI error %s (request %s): %s',
                            response.status_code, response.headers.get('request-id'), detail)
            raise UserError(_('Claude AI returned an error (%(status)s): %(message)s',
                              status=response.status_code, message=detail))
        stop_reason = body.get('stop_reason')
        if stop_reason == 'refusal':
            raise UserError(_('Claude AI declined this request.'))
        if stop_reason == 'max_tokens':
            raise UserError(_('Claude AI ran out of room for this dashboard. Try a smaller request.'))
        text = ''.join(
            block.get('text', '') for block in body.get('content') or [] if block.get('type') == 'text'
        )
        if not text:
            raise UserError(_('Claude AI returned an empty answer.'))
        return text

    @api.model
    def _ai_ask_gemini(self, key, system, prompt, schema):
        configured = self.env['ir.config_parameter'].sudo().get_param(GEMINI_MODEL_PARAM)
        candidates = [configured] if configured else GEMINI_MODELS
        payload = {
            'systemInstruction': {'parts': [{'text': system}]},
            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {
                'responseMimeType': 'application/json',
                'responseJsonSchema': schema,
                'temperature': 0.2,
            },
        }
        error_message = _('No Gemini model was available.')
        for model in candidates:
            try:
                response = requests.post(
                    GEMINI_URL % model, json=payload, timeout=AI_TIMEOUT,
                    headers={'x-goog-api-key': key},
                )
            except requests.exceptions.RequestException as error:
                raise UserError(_('Could not reach Google Gemini: %s', error)) from error
            if response.status_code == 404:
                error_message = _('Gemini model %s is not available.', model)
                continue
            if response.status_code == 400 and 'API_KEY_INVALID' in response.text:
                raise UserError(_('Google Gemini rejected the API key.'))
            if response.status_code == 400 and 'responseJsonSchema' in payload['generationConfig']:
                # Older models reject some schema keywords; the prompt still
                # describes the expected JSON, so ask again without it.
                payload['generationConfig'].pop('responseJsonSchema')
                response = requests.post(
                    GEMINI_URL % model, json=payload, timeout=AI_TIMEOUT,
                    headers={'x-goog-api-key': key},
                )
            if response.status_code in (401, 403):
                raise UserError(_('Google Gemini rejected the API key.'))
            if response.status_code != 200:
                try:
                    detail = response.json().get('error', {}).get('message', response.text)
                except ValueError:
                    detail = response.text
                _logger.warning('Gemini error %s: %s', response.status_code, detail)
                raise UserError(_('Google Gemini returned an error (%(status)s): %(message)s',
                                  status=response.status_code, message=detail[:300]))
            body = response.json()
            candidate = (body.get('candidates') or [{}])[0]
            parts = (candidate.get('content') or {}).get('parts') or []
            text = ''.join(part.get('text', '') for part in parts if not part.get('thought'))
            if not text:
                reason = candidate.get('finishReason') or body.get('promptFeedback', {}).get('blockReason')
                raise UserError(_('Google Gemini returned an empty answer (%s).', reason or _('no reason')))
            return text
        raise UserError(error_message)

    @api.model
    def _ai_parse_json(self, text):
        text = (text or '').strip()
        fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
        if fenced:
            text = fenced.group(1).strip()
        if not text.startswith('{'):
            start, end = text.find('{'), text.rfind('}')
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except ValueError as error:
            raise UserError(_('The AI answer was not valid JSON.')) from error
        if not isinstance(data, dict):
            raise UserError(_('The AI answer was not a JSON object.'))
        return data

    # ------------------------------------------------------------------
    # Building the dashboard
    # ------------------------------------------------------------------
    @api.model
    def _ai_create_dashboard(self, design, allowed_models, prompt):
        """Create a dashboard from the AI ``design``; return it and warnings."""
        warnings = []
        specs = [w for w in (design.get('widgets') or []) if isinstance(w, dict)][:MAX_WIDGETS]
        if not specs:
            raise UserError(_('The AI answer did not contain any widgets.'))
        dashboard = self.create({
            'name': str(design.get('name') or prompt[:60]).strip()[:120],
            'description': str(design.get('description') or '').strip()[:500] or prompt[:500],
        })
        types = {t.code: t for t in self._ai_widget_types()}
        placed = []
        Widget = self.env['custom.dashboard.widget']
        for spec in specs:
            title = str(spec.get('title') or '').strip()[:120]
            widget_type = types.get(spec.get('type'))
            if not widget_type or widget_type.code == 'image':
                warnings.append(_('Skipped "%(title)s": unknown widget type "%(type)s".',
                                  title=title, type=spec.get('type')))
                continue
            try:
                vals = self._ai_widget_vals(spec, widget_type, allowed_models, warnings)
            except UserError as error:
                warnings.append(_('Skipped "%(title)s": %(reason)s', title=title or widget_type.name,
                                  reason=error.args[0]))
                continue
            vals.update(self._ai_place(spec, widget_type, placed))
            vals.update({'dashboard_id': dashboard.id, 'type_id': widget_type.id,
                         'name': title or widget_type.name})
            widget = Widget.create(vals)
            if not self._ai_check_data(widget, warnings):
                placed.pop()
                widget.unlink()
        if not dashboard.widget_ids:
            dashboard.unlink()
            raise UserError(_('None of the widgets the AI designed could be built:\n%s', '\n'.join(warnings)))
        return dashboard, warnings

    @api.model
    def _ai_place(self, spec, widget_type, placed):
        """Clamp the widget to the 12-column grid and move it down past any
        widget it would overlap."""
        def number(key, default):
            try:
                return int(spec.get(key))
            except (TypeError, ValueError):
                return default
        w = min(max(number('w', widget_type.default_width or 4), 1), COLUMNS)
        h = min(max(number('h', widget_type.default_height or 4), 1), 12)
        x = min(max(number('x', 0), 0), COLUMNS - w)
        y = max(number('y', 0), 0)

        def overlaps(y):
            return any(x < px + pw and px < x + w and y < py + ph and py < y + h
                       for px, py, pw, ph in placed)
        while overlaps(y):
            y += 1
        placed.append((x, y, w, h))
        return {'pos_x': x, 'pos_y': y, 'width': w, 'height': h}

    @api.model
    def _ai_widget_vals(self, spec, widget_type, allowed_models, warnings):
        mode = widget_type.data_mode
        vals = {}
        for key in ('subtitle', 'prefix', 'suffix', 'pivot_row_label', 'pivot_col_label'):
            if isinstance(spec.get(key), str) and spec[key].strip():
                vals[key] = spec[key].strip()[:120]
        for key in ('show_legend', 'show_values', 'show_border', 'show_shadow', 'pivot_show_all_rows',
                    'pivot_show_all_columns', 'pivot_hide_none_rows', 'pivot_hide_none_columns',
                    'pivot_hide_row_totals', 'pivot_hide_column_totals'):
            if isinstance(spec.get(key), bool):
                vals[key] = spec[key]
        for key in ('target', 'gauge_min', 'gauge_max'):
            if isinstance(spec.get(key), (int, float)) and not isinstance(spec.get(key), bool):
                vals[{'target': 'target_value'}.get(key, key)] = float(spec[key])
        if isinstance(spec.get('decimals'), int):
            vals['decimals'] = min(max(spec['decimals'], 0), 6)
        colors = [c for c in (spec.get('colors') or []) if isinstance(c, str) and HEX_COLOR.match(c)][:6]
        if colors:
            vals['custom_colors'] = True
            for fname, color in zip(['color', 'color_2', 'color_3', 'color_4', 'color_5', 'color_6'], colors):
                vals[fname] = color.lower()
        if mode == 'content':
            if widget_type.code == 'text':
                vals['text_content'] = spec.get('text_content') or '<p></p>'
            return vals

        model_name = spec.get('model')
        if model_name not in allowed_models:
            raise UserError(_('model "%s" is not available.', model_name))
        IrModel = self.env['ir.model']._get(model_name)
        Model = self.env[model_name]
        vals['model_id'] = IrModel.id

        def option(key, choices, target=None):
            if spec.get(key) in dict(choices):
                vals[target or key] = spec[key]

        def field(key, types, target, required=False):
            name = spec.get(key)
            if not name:
                if required:
                    raise UserError(_('it needs a "%s" field.', key))
                return None
            model_field = Model._fields.get(name)
            ir_field = self.env['ir.model.fields']._get(model_name, name) if model_field else None
            if not ir_field or not model_field.store or model_field.type not in types:
                if required:
                    raise UserError(_('"%(field)s" cannot be used as %(key)s.', field=name, key=key))
                warnings.append(_('Ignored field "%(field)s" (%(key)s) on %(model)s.',
                                  field=name, key=key, model=model_name))
                return None
            vals[target] = ir_field.id
            return model_field

        if mode == 'grouped':
            groupby = field('group_by', GROUPABLE_TYPES, 'groupby_field_id', required=True)
            if groupby.type in DATE_TYPES:
                option('group_by_interval', INTERVALS, 'groupby_interval')
            if widget_type.supports_series:
                series = field('series', GROUPABLE_TYPES, 'series_field_id', required=widget_type.requires_series)
                if series and series.type in DATE_TYPES:
                    option('series_interval', INTERVALS)
            option('sort', SORTS)
            option('pivot_row_sort', AXIS_SORTS)
            option('pivot_col_sort', AXIS_SORTS)
            if isinstance(spec.get('limit'), int) and spec['limit'] > 0:
                vals['limit'] = min(spec['limit'], 100)
        if mode in ('grouped', 'single', 'points', 'map'):
            if field('measure', MEASURE_TYPES, 'measure_field_id'):
                option('aggregate', AGGREGATES)
            if widget_type.uses_second_measure or mode == 'points':
                if field('measure2', MEASURE_TYPES, 'measure2_field_id'):
                    option('aggregate2', AGGREGATES)
        if mode == 'points' and isinstance(spec.get('limit'), int) and spec['limit'] > 0:
            vals['limit'] = min(spec['limit'], 2000)
        if mode == 'single' and spec.get('value_mode') == 'elapsed':
            vals['value_mode'] = 'elapsed'
            field('elapsed_field', DATE_TYPES, 'elapsed_field_id', required=True)
            option('elapsed_unit', ELAPSED_UNITS)
        if mode == 'map':
            option('map_level', MAP_LEVELS)
            if spec.get('map_address_path'):
                vals['map_address_path'] = str(spec['map_address_path']).strip()
            code = str(spec.get('map_country_code') or '').strip().upper()
            if code:
                country = self.env['res.country'].search([('code', '=', code)], limit=1)
                if country:
                    vals['map_country_id'] = country.id
        if spec.get('user_filter_scope') in dict(USER_SCOPES):
            vals['user_filter_scope'] = spec['user_filter_scope']
            if spec.get('user_filter_path'):
                vals['user_filter_path'] = str(spec['user_filter_path']).strip()
            elif model_name not in USER_FILTER_MODELS:
                vals.pop('user_filter_scope')
                warnings.append(_('Ignored the user filter on "%s": no user field given.', spec.get('title')))
        domain = spec.get('domain')
        if isinstance(domain, str) and domain.strip() not in ('', '[]'):
            vals['domain'] = domain.strip()
        return vals

    @api.model
    def _ai_check_data(self, widget, warnings):
        """Make sure the widget loads; drop a broken filter or user filter,
        and report False when the widget still cannot load."""
        def loads():
            try:
                with self.env.cr.savepoint():
                    data = widget._compute_data()
            except Exception as error:  # noqa: BLE001 - anything the AI built wrong
                _logger.info('AI widget %s failed: %s', widget.id, error)
                return False
            return not (isinstance(data, dict) and data.get('error'))

        if widget.data_mode == 'content' or loads():
            return True
        for fname, default, label in (('domain', '[]', _('filter')),
                                      ('user_filter_scope', False, _('user filter')),
                                      ('map_address_path', False, _('map address'))):
            if widget[fname] and widget[fname] != default:
                widget.write({fname: default, **({'user_filter_path': False} if fname == 'user_filter_scope' else {})})
                warnings.append(_('Removed the %(what)s of "%(title)s" because it did not work.',
                                  what=label, title=widget.name))
                if loads():
                    return True
        warnings.append(_('Skipped "%s": its data could not be loaded.', widget.name))
        return False

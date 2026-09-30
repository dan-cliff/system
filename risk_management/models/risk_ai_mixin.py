import json
import logging

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL = 'claude-sonnet-5'
CLAUDE_API_VERSION = '2023-06-01'


def ai_generate_control_description(api_key, control_name):
    """Ask Claude for a detailed, practical description of a named risk control.

    Returns the description text, or '' if the call fails or yields nothing usable -
    callers should treat this as best-effort and not block on it.
    """
    prompt = (
        "You are a Work Health & Safety risk assessor for a youth Scouting organisation in "
        "Australia. Write a detailed, practical description (2-4 sentences) of the following "
        "risk control, explaining what implementing it actually involves.\n\n"
        f"Control: {control_name}\n\n"
        "Respond with ONLY the description text - no heading, no quotes, no markdown."
    )
    try:
        response = requests.post(
            CLAUDE_API_URL,
            headers={
                'x-api-key': api_key,
                'anthropic-version': CLAUDE_API_VERSION,
                'content-type': 'application/json',
            },
            json={
                'model': CLAUDE_MODEL,
                'max_tokens': 512,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        _logger.warning('Claude API call failed while describing control %r: %s', control_name, exc)
        return ''
    if response.status_code >= 400:
        _logger.warning(
            'Claude API returned %s while describing control %r', response.status_code, control_name,
        )
        return ''
    payload = response.json()
    text = ''.join(
        block.get('text', '') for block in payload.get('content', []) if block.get('type') == 'text'
    )
    return text.strip()


class RiskAiMixin(models.AbstractModel):
    _name = 'risk.ai.mixin'
    _description = 'Risk AI Generation Mixin'

    # Set by each concrete model: the risk.line.mixin model to create rows on,
    # and the field on that model linking back to this record.
    _ai_line_model = None
    _ai_line_parent_field = None

    summary_of_activity = fields.Text(
        string='Summary of Activity',
        help='Describe the activity or event. Used as context when generating risks and '
             'controls by AI.',
    )
    ai_available = fields.Boolean(compute='_compute_ai_available')

    def _compute_ai_available(self):
        installed = bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'claude_ai_settings'), ('state', '=', 'installed'),
        ]))
        for record in self:
            record.ai_available = installed

    def action_generate_risks_ai(self):
        self.ensure_one()
        if not self.summary_of_activity:
            raise UserError('Add a Summary of Activity before generating risks and controls.')
        api_key = self.env['ir.config_parameter'].sudo().get_param('claude_ai_settings.api_key')
        if not api_key:
            raise UserError(
                'Set a Claude AI API Key first (Settings > Technical > Claude AI Settings).'
            )
        risks_data = self._ai_fetch_risks(api_key)
        self._ai_create_lines(risks_data)
        return True

    def _ai_fetch_risks(self, api_key):
        self.ensure_one()
        existing_types = self.env['risk.type'].search([]).mapped('name')
        existing_subtypes = [
            f"{subtype.risk_type_id.name} > {subtype.name}"
            for subtype in self.env['risk.subtype'].search([], order='risk_type_id, name')
        ]
        existing_controls = self.env['risk.control'].search([]).mapped('name')
        likelihoods = self.env['risk.likelihood'].search([], order='sequence, value').mapped('name')
        consequences = self.env['risk.consequence'].search([], order='sequence, value').mapped('name')
        prompt = self._ai_build_prompt(
            existing_types, existing_subtypes, existing_controls, likelihoods, consequences,
        )
        try:
            response = requests.post(
                CLAUDE_API_URL,
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': CLAUDE_API_VERSION,
                    'content-type': 'application/json',
                },
                json={
                    'model': CLAUDE_MODEL,
                    'max_tokens': 8192,
                    'messages': [{'role': 'user', 'content': prompt}],
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            _logger.warning('Claude API call failed: %s', exc)
            raise UserError('Could not reach the Claude API: %s' % exc) from exc
        if response.status_code >= 400:
            try:
                error_detail = response.json().get('error', {}).get('message') or response.text
            except ValueError:
                error_detail = response.text
            _logger.warning('Claude API returned %s: %s', response.status_code, error_detail)
            raise UserError('Claude API error (%s): %s' % (response.status_code, error_detail))
        payload = response.json()
        text = ''.join(
            block.get('text', '') for block in payload.get('content', []) if block.get('type') == 'text'
        )
        return self._ai_parse_response(text)

    def _ai_build_prompt(self, existing_types, existing_subtypes, existing_controls, likelihoods, consequences):
        self.ensure_one()
        return (
            "You are a Work Health & Safety risk assessor for a youth Scouting organisation in "
            "Australia. Given the activity summary below, identify the key risks and, for each "
            "risk, suggest practical controls and estimate the INHERENT risk - i.e. how likely "
            "and how severe this risk would be if NONE of the suggested controls (or any other "
            "controls) were in place yet.\n\n"
            f"Activity summary:\n{self.summary_of_activity}\n\n"
            "Existing Risk Types already in our system - reuse one of these names if it clearly "
            "fits, otherwise suggest a new short Risk Type name:\n"
            + ', '.join(existing_types or ['(none yet)']) + "\n\n"
            "Existing Risk Subtypes already in our system, shown as 'Risk Type > Subtype' - every "
            "risk MUST have a subtype, so reuse one of these below if it fits the risk_type you "
            "picked, otherwise suggest a new short Subtype name that belongs under that Risk Type:\n"
            + ', '.join(existing_subtypes or ['(none yet)']) + "\n\n"
            "Existing Controls already in our library - reuse a name below if it fits, otherwise "
            "suggest a new short Control name:\n"
            + ', '.join(existing_controls or ['(none yet)']) + "\n\n"
            "Likelihood bands (choose exactly one of these existing names for inherent_likelihood, "
            "lowest to highest): " + ', '.join(likelihoods or ['(none configured)']) + "\n\n"
            "Consequence bands (choose exactly one of these existing names for inherent_consequence, "
            "lowest to highest): " + ', '.join(consequences or ['(none configured)']) + "\n\n"
            "Respond with ONLY a JSON array (no other text, no markdown code fences), where each "
            "item has this exact shape:\n"
            '{"name": "short risk name", "unwanted_event": "what could go wrong", '
            '"description": "1-2 sentence description of the risk", '
            '"risk_type": "Risk Type name", '
            '"risk_subtype": "Risk Subtype name, belonging to that Risk Type", '
            '"inherent_likelihood": "one of the Likelihood band names above", '
            '"inherent_consequence": "one of the Consequence band names above", '
            '"controls": ["Control name", "Control name"]}'
        )

    def _ai_parse_response(self, text):
        text = (text or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lower().startswith('json'):
                text = text[4:]
            text = text.strip()
        data = self._ai_try_parse_json(text)
        if data is None:
            _logger.warning('Could not parse Claude response as JSON: %s', text[:2000])
            raise UserError(
                'The AI response could not be understood (it may have included extra text, or '
                'been cut off if a lot of risks were generated at once). Please try again - if '
                'it keeps happening, try a shorter Summary of Activity.\n\n'
                'Start of the raw response:\n%s' % text[:500]
            )
        if isinstance(data, dict):
            # Claude sometimes wraps the array, e.g. {"risks": [...]} - unwrap it.
            list_values = [value for value in data.values() if isinstance(value, list)]
            if len(list_values) == 1:
                data = list_values[0]
        if not isinstance(data, list):
            raise UserError('The AI response was not in the expected format. Please try again.')
        return data

    def _ai_try_parse_json(self, text):
        try:
            return json.loads(text)
        except ValueError:
            pass
        # Fall back to the outermost [...] or {...} in case the model added stray text
        # around the JSON despite being asked not to.
        for open_char, close_char in ('[', ']'), ('{', '}'):
            start = text.find(open_char)
            end = text.rfind(close_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except ValueError:
                    continue
        return None

    def _ai_create_lines(self, risks_data):
        self.ensure_one()
        if not self._ai_line_model or not self._ai_line_parent_field:
            return
        Line = self.env[self._ai_line_model]
        Control = self.env['risk.control']
        RiskType = self.env['risk.type']
        RiskSubtype = self.env['risk.subtype']
        Likelihood = self.env['risk.likelihood']
        Consequence = self.env['risk.consequence']
        for risk in risks_data:
            if not isinstance(risk, dict) or not risk.get('name'):
                continue
            control_ids = []
            control_names = [name for name in (risk.get('controls') or []) if isinstance(name, str) and name.strip()]
            for control_name in control_names:
                control_name = control_name.strip()
                control = Control.search([('name', '=ilike', control_name)], limit=1)
                if not control:
                    control = Control.create({'name': control_name})
                control_ids.append(control.id)
            risk_type = self.env['risk.type']
            type_name = (risk.get('risk_type') or '').strip()
            if type_name:
                risk_type = RiskType.search([('name', '=ilike', type_name)], limit=1)
                if not risk_type:
                    risk_type = RiskType.create({'name': type_name})
            risk_subtype = self.env['risk.subtype']
            subtype_name = (risk.get('risk_subtype') or '').strip()
            if subtype_name and risk_type:
                risk_subtype = RiskSubtype.search([
                    ('risk_type_id', '=', risk_type.id), ('name', '=ilike', subtype_name),
                ], limit=1)
                if not risk_subtype:
                    risk_subtype = RiskSubtype.create({'name': subtype_name, 'risk_type_id': risk_type.id})
            likelihood = self.env['risk.likelihood']
            likelihood_name = (risk.get('inherent_likelihood') or '').strip()
            if likelihood_name:
                likelihood = Likelihood.search([('name', '=ilike', likelihood_name)], limit=1)
            consequence = self.env['risk.consequence']
            consequence_name = (risk.get('inherent_consequence') or '').strip()
            if consequence_name:
                consequence = Consequence.search([('name', '=ilike', consequence_name)], limit=1)
            # Residual likelihood/consequence are deliberately left empty here - they depend on
            # which controls actually get implemented, which is a human judgement call.
            Line.create({
                self._ai_line_parent_field: self.id,
                'name': risk.get('name'),
                'unwanted_event': risk.get('unwanted_event') or '',
                'description': risk.get('description') or '',
                'risk_type_id': risk_type.id if risk_type else False,
                'risk_subtype_id': risk_subtype.id if risk_subtype else False,
                'inherent_likelihood_id': likelihood.id if likelihood else False,
                'inherent_consequence_id': consequence.id if consequence else False,
                'control_ids': [(6, 0, control_ids)],
                'control_summary': ', '.join(control_names),
            })

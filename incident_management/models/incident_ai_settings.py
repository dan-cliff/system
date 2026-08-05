# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

PARAM_OPENAI = 'incident_management.openai_api_key'
PARAM_GOOGLE = 'incident_management.google_api_key'


class IncidentAISettings(models.TransientModel):
    """Wizard-style settings form for the AI integration API keys."""
    _name = 'incident.ai.settings'
    _description = 'Incident Management AI Settings'

    openai_api_key = fields.Char(
        'ChatGPT (OpenAI) API Key',
        help='Your OpenAI API key (starts with sk-). '
             'Stored securely as a system parameter.',
    )
    google_api_key = fields.Char(
        'Google Gemini API Key',
        help='Your Google Gemini API key (starts with AIza). '
             'Stored securely as a system parameter.',
    )
    openai_from_ai_settings = fields.Boolean(
        string='OpenAI Key from AI Settings',
        compute='_compute_ai_key_sources',
        help='True when an OpenAI key is configured in the central AI app settings.',
    )
    google_from_ai_settings = fields.Boolean(
        string='Google Gemini Key from AI Settings',
        compute='_compute_ai_key_sources',
        help='True when a Google Gemini key is configured in the central AI app settings.',
    )

    @api.depends_context('uid')
    def _compute_ai_key_sources(self):
        params = self.env['ir.config_parameter'].sudo()
        openai_key = params.get_param('ai.openai_key', default='')
        google_key = params.get_param('ai.google_key', default='')
        for rec in self:
            rec.openai_from_ai_settings = bool(openai_key)
            rec.google_from_ai_settings = bool(google_key)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        if 'openai_api_key' in fields_list:
            res['openai_api_key'] = params.get_param(PARAM_OPENAI, default='')
        if 'google_api_key' in fields_list:
            res['google_api_key'] = params.get_param(PARAM_GOOGLE, default='')
        return res

    def action_save(self):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param(PARAM_OPENAI, self.openai_api_key or '')
        params.set_param(PARAM_GOOGLE, self.google_api_key or '')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Settings Saved'),
                'message': _('The AI API keys have been saved.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

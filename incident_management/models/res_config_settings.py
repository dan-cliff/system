# -*- coding: utf-8 -*-
from odoo import api, fields, models

PARAM_OPENAI = 'incident_management.openai_api_key'
PARAM_GOOGLE = 'incident_management.google_api_key'


class ResConfigSettings(models.TransientModel):
    """Extends the global Settings page with an Incidents section."""

    _inherit = 'res.config.settings'

    im_openai_api_key = fields.Char(
        string='ChatGPT (OpenAI) API Key',
        config_parameter=PARAM_OPENAI,
        help='Your OpenAI API key (starts with sk-). '
             'Used to generate AI corrective action recommendations via ChatGPT. '
             'Stored securely as a system parameter.',
    )
    im_google_api_key = fields.Char(
        string='Gemini API Key (Incident AI)',
        config_parameter=PARAM_GOOGLE,
        help='Your Google Gemini API key (starts with AIza). '
             'Used as a fallback AI provider for corrective action recommendations. '
             'Stored securely as a system parameter.',
    )
    im_openai_from_ai_settings = fields.Boolean(
        string='OpenAI Key from AI Settings',
        compute='_compute_im_ai_key_sources',
        help='True when an OpenAI key is configured in the central AI app settings.',
    )
    im_google_from_ai_settings = fields.Boolean(
        string='Google Gemini Key from AI Settings',
        compute='_compute_im_ai_key_sources',
        help='True when a Google Gemini key is configured in the central AI app settings.',
    )

    @api.depends_context('uid')
    def _compute_im_ai_key_sources(self):
        params = self.env['ir.config_parameter'].sudo()
        openai_key = params.get_param('ai.openai_key', default='')
        google_key = params.get_param('ai.google_key', default='')
        for rec in self:
            rec.im_openai_from_ai_settings = bool(openai_key)
            rec.im_google_from_ai_settings = bool(google_key)

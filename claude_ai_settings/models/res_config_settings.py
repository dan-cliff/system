from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    claude_api_key = fields.Char(
        string='Claude AI API Key',
        config_parameter='claude_ai_settings.api_key',
        help='Used by other apps in this database to authenticate with the Claude AI API '
             'for AI agent features.',
    )
    gemini_api_key = fields.Char(
        string='Google Gemini API Key',
        config_parameter='claude_ai_settings.gemini_api_key',
        help='Used by other apps in this database to authenticate with the Google Gemini API '
             'for AI agent features.',
    )

    def action_open_anthropic_console(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://console.anthropic.com/settings/keys',
            'target': 'new',
        }

    def action_open_google_ai_studio(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://aistudio.google.com/apikey',
            'target': 'new',
        }

from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    anthropic_key_enabled = fields.Boolean(
        string="Enable custom Anthropic API key",
        compute='_compute_anthropic_key_enabled',
        readonly=False,
        groups='base.group_system',
    )
    anthropic_key = fields.Char(
        string="Anthropic API key",
        config_parameter='ai.anthropic_key',
        readonly=False,
        groups='base.group_system',
    )

    def _compute_anthropic_key_enabled(self):
        for record in self:
            record.anthropic_key_enabled = bool(record.anthropic_key)

    def action_open_anthropic_wizard(self):
        """Open the Anthropic sign-in wizard from the AI settings page."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign in to Anthropic'),
            'res_model': 'anthropic.auth.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

import logging
import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_CONSOLE_URL = "https://console.anthropic.com/settings/keys"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAuthWizard(models.TransientModel):
    _name = 'anthropic.auth.wizard'
    _description = 'Sign in to Anthropic'

    api_key = fields.Char(
        string='API Key',
        help='Paste your Anthropic API key here. It starts with sk-ant-.',
    )
    # Populated after a successful validation so the view can surface feedback
    # without closing the wizard prematurely.
    key_hint = fields.Char(
        string='Current Key',
        compute='_compute_key_hint',
    )
    has_existing_key = fields.Boolean(
        compute='_compute_key_hint',
    )

    def _compute_key_hint(self):
        """Show a masked hint of the currently saved key, if any."""
        for rec in self:
            existing = (
                self.env['ir.config_parameter']
                .sudo()
                .get_param('ai.anthropic_key', default='')
            )
            if existing:
                rec.has_existing_key = True
                # Show first 12 + last 4 characters, mask the rest
                visible_end = existing[-4:] if len(existing) >= 4 else existing
                rec.key_hint = existing[:12] + '••••••••••••' + visible_end
            else:
                rec.has_existing_key = False
                rec.key_hint = ''

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_console(self):
        """Open the Anthropic Console API keys page in a new browser tab."""
        return {
            'type': 'ir.actions.act_url',
            'url': ANTHROPIC_CONSOLE_URL,
            'target': 'new',
        }

    def action_validate_and_save(self):
        """Validate the API key against Anthropic, then save it if accepted."""
        self.ensure_one()

        api_key = (self.api_key or '').strip()
        if not api_key:
            raise UserError(_("Please paste your Anthropic API key before saving."))

        # ── Call Anthropic's models list endpoint — cheap, no token cost ──────
        try:
            response = requests.get(
                ANTHROPIC_MODELS_URL,
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': ANTHROPIC_VERSION,
                },
                timeout=15,
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _("Cannot reach Anthropic (connection error). "
                  "Please check your internet connection and try again.")
            )
        except requests.exceptions.Timeout:
            raise UserError(
                _("The request to Anthropic timed out. Please try again.")
            )
        except Exception as exc:
            raise UserError(_("Unexpected error connecting to Anthropic: %s") % exc)

        # ── Interpret the response ────────────────────────────────────────────
        if response.status_code == 200:
            pass  # valid key — fall through to save
        elif response.status_code == 401:
            raise UserError(
                _("Invalid API key — Anthropic did not accept it.\n\n"
                  "Please check that you copied the key correctly and try again.")
            )
        elif response.status_code == 403:
            raise UserError(
                _("This API key was rejected with a permissions error (HTTP 403).\n\n"
                  "Make sure billing is enabled on your Anthropic account and that "
                  "the key has not been restricted.")
            )
        elif response.status_code == 429:
            raise UserError(
                _("Anthropic rate limit reached (HTTP 429). "
                  "Please wait a moment and try again.")
            )
        else:
            try:
                err_detail = response.json().get('error', {}).get('message', response.text)
            except Exception:
                err_detail = response.text or str(response.status_code)
            raise UserError(
                _("Anthropic returned an error (HTTP %s):\n%s")
                % (response.status_code, err_detail)
            )

        # ── Save the validated key ────────────────────────────────────────────
        self.env['ir.config_parameter'].sudo().set_param('ai.anthropic_key', api_key)
        _logger.info("Anthropic API key saved successfully by user %s", self.env.user.login)

        # Close the wizard and show a success banner; soft-reload refreshes the
        # settings form so the key field and toggle update immediately.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Anthropic Connected'),
                'message': _('Your Anthropic API key has been validated and saved.'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'soft_reload',
                },
            },
        }

    def action_clear_key(self):
        """Remove the stored Anthropic API key."""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('ai.anthropic_key', '')
        _logger.info("Anthropic API key cleared by user %s", self.env.user.login)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Key Removed'),
                'message': _('The Anthropic API key has been removed.'),
                'type': 'info',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'soft_reload',
                },
            },
        }

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REGION_LOGIN_HOSTS = {
    'us': 'api.bambulab.com',
    'eu': 'api.bambulab.com',
    'ap': 'api.bambulab.com',
    'cn': 'api.bambulab.cn',
}


class BambuAuthWizard(models.TransientModel):
    _name = 'print.printer.bambu.auth.wizard'
    _description = 'Bambu Cloud Authentication'

    printer_id = fields.Many2one(
        'print.printer',
        string='Printer',
        required=True,
        readonly=True,
    )
    printer_name = fields.Char(related='printer_id.name', string='Printer', readonly=True)
    cloud_region = fields.Selection(
        [('us', 'Americas'), ('eu', 'Europe'), ('cn', 'China'), ('ap', 'Asia Pacific')],
        string='Cloud Region',
        required=True,
        default='eu',
    )
    email = fields.Char(string='Bambu Account Email', required=True)
    password = fields.Char(string='Password', required=True)

    # ── Step 2 ────────────────────────────────────────────────────────────────
    step = fields.Selection(
        [('credentials', 'Sign In'), ('verify', 'Verify Email')],
        default='credentials',
        required=True,
    )
    verification_code = fields.Char(
        string='Verification Code',
        help='6-digit code sent to your Bambu account email address',
    )

    # ─────────────────────────────────────────────────────────────────────────

    @api.onchange('printer_id')
    def _onchange_printer_id(self):
        if self.printer_id and self.printer_id.cloud_region:
            self.cloud_region = self.printer_id.cloud_region

    def _get_login_url(self):
        host = REGION_LOGIN_HOSTS.get(self.cloud_region, 'api.bambulab.com')
        return 'https://%s/v1/user-service/user/login' % host

    def _reopen(self):
        """Return an action that reopens this same wizard record."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _post_credentials(self):
        """POST account + password to the Bambu login endpoint and return the parsed JSON."""
        try:
            import requests
        except ImportError:
            raise UserError(
                _('The "requests" Python package is required.\n'
                  'Install it with: pip install requests')
            )
        # Bambu's API requires client identification headers; plain requests are rejected.
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'bambu_network_agent/01.09.05.01',
            'X-BBL-Client-Name': 'OrcaSlicer',
            'X-BBL-Client-Type': 'slicer',
            'X-BBL-Client-Version': '01.09.05.51',
            'X-BBL-Language': 'en-US',
            'X-BBL-OS-Type': 'linux',
            'X-BBL-OS-Version': '6.2.0',
            'X-BBL-Agent-Version': '01.09.05.01',
            'X-BBL-Executable-info': '{}',
            'X-BBL-Agent-OS-Type': 'linux',
        }
        try:
            resp = requests.post(
                self._get_login_url(),
                json={'account': self.email, 'password': self.password, 'apiError': ''},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            raise UserError(_('Bambu Cloud login request failed: %s') % str(e))
        return resp.json()

    # ── Step 1: submit credentials ────────────────────────────────────────────

    def action_authenticate(self):
        """POST credentials to Bambu Cloud. If a verification code is required,
        advance to step 2 and keep the wizard open."""
        self.ensure_one()
        data = self._post_credentials()
        login_type = data.get('loginType', '')
        token = data.get('accessToken') or data.get('token')

        # Bambu requires an emailed verification code before issuing a token
        if login_type == 'verifyCode' and not token:
            self.write({'step': 'verify'})
            return self._reopen()

        # 2FA via TOTP (not supported here)
        if data.get('tfaKey') and not token:
            raise UserError(
                _('This Bambu account has two-factor authentication (TOTP/authenticator app) '
                  'enabled.\n\nPlease disable 2FA temporarily in your Bambu account settings, '
                  'authenticate here to save the token, then re-enable 2FA.')
            )

        if not token:
            raise UserError(
                _('Bambu Cloud did not return a token. '
                  'Please check your email address and password.\n\nResponse: %s') % str(data)
            )

        return self._save_token(token)

    # ── Step 2: submit verification code ─────────────────────────────────────

    def action_verify(self):
        """POST credentials + emailed verification code to obtain the access token."""
        self.ensure_one()
        if not self.verification_code:
            raise UserError(_('Please enter the verification code sent to your email.'))

        try:
            import requests
        except ImportError:
            raise UserError(
                _('The "requests" Python package is required.\n'
                  'Install it with: pip install requests')
            )

        try:
            resp = requests.post(
                self._get_login_url(),
                json={
                    'account': self.email,
                    'password': self.password,
                    'code': self.verification_code,
                },
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            raise UserError(_('Bambu Cloud verification request failed: %s') % str(e))

        data = resp.json()
        token = data.get('accessToken') or data.get('token')

        if not token:
            raise UserError(
                _('Verification failed. Please check the code and try again.\n\n'
                  'Response: %s') % str(data)
            )

        return self._save_token(token)

    def action_resend_code(self):
        """Re-POST credentials to trigger Bambu to send a fresh verification email."""
        self.ensure_one()
        self._post_credentials()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Code Resent'),
                'message': _('A new verification code has been sent to %s.') % self.email,
                'type': 'success',
                'sticky': False,
            },
        }

    # ── Shared ────────────────────────────────────────────────────────────────

    def _save_token(self, token):
        self.printer_id.write({
            'cloud_token': token,
            'cloud_region': self.cloud_region,
        })
        _logger.info(
            'Bambu Cloud token saved for printer %s (region: %s)',
            self.printer_id.name,
            self.cloud_region,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Authentication Successful'),
                'message': _('Bambu Cloud token saved for printer "%s".') % self.printer_id.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

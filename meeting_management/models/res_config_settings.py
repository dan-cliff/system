from odoo import models, fields, api, _
from odoo.exceptions import UserError
import urllib.parse


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Microsoft / Teams credentials ────────────────────────────────────────
    ms_client_id = fields.Char(
        string='Azure App Client ID',
        config_parameter='meeting_management.ms_client_id',
    )
    ms_client_secret = fields.Char(
        string='Azure App Client Secret',
        config_parameter='meeting_management.ms_client_secret',
    )
    ms_tenant_id = fields.Char(
        string='Azure Tenant ID',
        config_parameter='meeting_management.ms_tenant_id',
        default='common',
    )
    ms_redirect_uri = fields.Char(
        string='OAuth Redirect URI',
        config_parameter='meeting_management.ms_redirect_uri',
        help='Must match the redirect URI registered in your Azure App. '
             'Typically: https://yourdomain.com/meeting_management/ms_oauth/callback',
    )
    ms_connected = fields.Boolean(
        string='Microsoft Account Connected',
        compute='_compute_ms_connected',
    )
    ms_token_expiry = fields.Char(
        string='Token Expiry',
        compute='_compute_ms_connected',
    )

    @api.depends()
    def _compute_ms_connected(self):
        ICP = self.env['ir.config_parameter'].sudo()
        token = ICP.get_param('meeting_management.ms_access_token', '')
        expiry = ICP.get_param('meeting_management.ms_token_expiry', '')
        for rec in self:
            rec.ms_connected = bool(token)
            rec.ms_token_expiry = expiry[:19].replace('T', ' ') if expiry else ''

    def action_connect_microsoft(self):
        """Redirect to Microsoft OAuth authorization URL."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        client_id = ICP.get_param('meeting_management.ms_client_id', '')
        tenant_id = ICP.get_param('meeting_management.ms_tenant_id', 'common')
        redirect_uri = ICP.get_param('meeting_management.ms_redirect_uri', '')

        if not client_id:
            raise UserError(_('Please save the Azure App Client ID before connecting.'))
        if not redirect_uri:
            raise UserError(_('Please save the OAuth Redirect URI before connecting.'))

        scope = 'offline_access OnlineMeetings.ReadWrite Calendars.ReadWrite User.Read'
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': scope,
            'response_mode': 'query',
        }
        auth_url = (
            f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?'
            + urllib.parse.urlencode(params)
        )
        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'self',
        }

    def action_disconnect_microsoft(self):
        """Clear stored Microsoft tokens."""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('meeting_management.ms_access_token', '')
        ICP.set_param('meeting_management.ms_refresh_token', '')
        ICP.set_param('meeting_management.ms_token_expiry', '')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Disconnected'),
                'message': _('Microsoft account has been disconnected.'),
                'type': 'warning',
            },
        }

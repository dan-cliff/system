from odoo import api, fields, models

from .offline_access_device import DEFAULT_HEARTBEAT_MINUTES, DEFAULT_STALE_DAYS, DEFAULT_THEME_COLOR


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    offline_access_enabled = fields.Boolean(
        string='Offline Access', config_parameter='offline_access.enabled')
    offline_access_theme_color = fields.Char(
        string='App Colour', config_parameter='offline_access.theme_color', default=DEFAULT_THEME_COLOR)
    offline_access_heartbeat_minutes = fields.Integer(
        string='Report In Every (minutes)', config_parameter='offline_access.heartbeat_minutes',
        default=DEFAULT_HEARTBEAT_MINUTES)
    offline_access_stale_days = fields.Integer(
        string='Stale After (days)', config_parameter='offline_access.stale_days',
        default=DEFAULT_STALE_DAYS)
    # Stored as a public attachment rather than a config parameter: the app
    # icon is served to browsers before anyone has signed in.
    offline_access_icon = fields.Binary(string='App Icon', attachment=False)
    offline_access_device_count = fields.Integer(compute='_compute_offline_access_device_count')

    def _compute_offline_access_device_count(self):
        count = self.env['offline.access.device'].search_count([('state', '!=', 'revoked')])
        for settings in self:
            settings.offline_access_device_count = count

    @api.model
    def get_values(self):
        res = super().get_values()
        icon = self.env['offline.access.device']._get_offline_access_config()['icon']
        res['offline_access_icon'] = icon.datas if icon else False
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        icon = self.env['offline.access.device']._get_offline_access_config()['icon']
        if (icon.datas if icon else False) == (self.offline_access_icon or False):
            return
        if self.offline_access_icon:
            new_icon = self.env['ir.attachment'].sudo().create({
                'name': 'offline_access_icon',
                'datas': self.offline_access_icon,
                'public': True,
            })
            ICP.set_param('offline_access.icon_attachment_id', new_icon.id)
        else:
            ICP.set_param('offline_access.icon_attachment_id', False)
        icon.unlink()

    def action_open_offline_access_devices(self):
        return self.env['ir.actions.act_window']._for_xml_id('offline_access.action_offline_access_device')

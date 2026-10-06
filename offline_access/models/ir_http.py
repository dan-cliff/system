from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the web client whether offline access is on, and how often to
        report in, without an extra RPC."""
        session_info = super().session_info()
        if session_info.get('is_internal_user'):
            Device = self.env['offline.access.device']
            config = Device._get_offline_access_config()
            session_info['offline_access'] = {
                'enabled': config['enabled'],
                'heartbeat_minutes': config['heartbeat_minutes'],
                'theme_color': config['theme_color'],
                'icon_version': config['icon_version'],
                'app_version': Device._get_service_worker_extension()[1] if config['enabled'] else False,
            }
        return session_info

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the web client which apps' lists the user may customise, and
        the layouts' version (part of the browser's view cache key)."""
        session_info = super().session_info()
        if self.env.user._is_internal():
            session_info['list_column_config'] = self.env['list.column.app']._session_info()
        return session_info

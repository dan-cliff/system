from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Expose each allowed company's toolbar colour to the web client, so
        the navbar can be coloured for the active company without an extra RPC."""
        session_info = super().session_info()
        allowed = session_info.get('user_companies', {}).get('allowed_companies')
        if allowed:
            companies = self.env['res.company'].sudo().browse(list(allowed))
            for company in companies:
                allowed[company.id]['toolbar_color'] = company.toolbar_color or False
        return session_info

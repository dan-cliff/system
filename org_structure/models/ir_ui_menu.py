from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    # Keep every user's App Specific Scoping list in step with installed apps.
    @api.model_create_multi
    def create(self, vals_list):
        menus = super().create(vals_list)
        if any(not menu.parent_id and menu.web_icon for menu in menus):
            self.env['res.users.org.scope']._sync_app_lines()
        return menus

    def write(self, vals):
        res = super().write(vals)
        if {'parent_id', 'web_icon', 'active'} & set(vals):
            self.env['res.users.org.scope']._sync_app_lines()
        return res

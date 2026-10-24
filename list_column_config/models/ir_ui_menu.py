from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    # Apps (top-level menus) come and go with their modules: have the cron
    # give new apps their List Columns privilege and remove those of old ones.
    def _list_column_sync_apps_later(self):
        cron = self.env.ref('list_column_config.ir_cron_list_column_sync_apps', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model_create_multi
    def create(self, vals_list):
        menus = super().create(vals_list)
        if any(not menu.parent_id for menu in menus):
            self._list_column_sync_apps_later()
        return menus

    def write(self, vals):
        roots = any(not menu.parent_id for menu in self)
        res = super().write(vals)
        if 'parent_id' in vals and (roots or not vals['parent_id']):
            self._list_column_sync_apps_later()
        return res

    def unlink(self):
        roots = any(not menu.parent_id for menu in self)
        res = super().unlink()
        if roots:
            self._list_column_sync_apps_later()
        return res

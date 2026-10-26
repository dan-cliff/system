from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        # Notification Templates are managed by Workflow Automation when it is installed.
        visible = super()._visible_menu_ids(debug=debug)
        menu = self.env.ref('advanced_actions.menu_advanced_action_notification', raise_if_not_found=False)
        if menu and menu.id in visible and not self.env['advanced.action.notification']._notifications_enabled():
            visible = type(visible)(set(visible) - {menu.id})
        return visible

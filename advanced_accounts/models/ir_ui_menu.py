from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        # Advanced Accounts takes over from the Contacts app: hide its app menu.
        # Contacts stays installed, since other apps use its partners and views.
        visible = super()._visible_menu_ids(debug=debug)
        menu = self.env.ref('contacts.menu_contacts', raise_if_not_found=False)
        if menu and menu.id in visible:
            visible = type(visible)(set(visible) - {menu.id})
        return visible

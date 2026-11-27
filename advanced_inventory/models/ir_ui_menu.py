# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    """Inventory takes the place of Odoo's Inventory app on the home screen.

    Odoo's Inventory module stays installed (Purchase, Sales, Manufacturing,
    Point of Sale, ... need it) but its root menu is archived. Every menu that
    Odoo or another app puts under it (now or when installed or upgraded
    later) lands under this app's Inventory menu instead."""
    _inherit = 'ir.ui.menu'

    @api.model
    def _inventory_roots(self):
        if self.env.context.get('inventory_menu_release'):  # uninstalling: let Odoo's Inventory have them back
            return None, None
        stock_root = self.env.ref('stock.menu_stock_root', raise_if_not_found=False)
        root = self.env.ref('advanced_inventory.menu_inventory_root', raise_if_not_found=False)
        return (stock_root, root) if stock_root and root else (None, None)

    @api.model
    def _inventory_redirect(self, vals):
        if vals.get('parent_id'):
            stock_root, root = self._inventory_roots()
            if stock_root and vals['parent_id'] == stock_root.id:
                vals = dict(vals, parent_id=root.id)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._inventory_redirect(vals) for vals in vals_list])

    def write(self, vals):
        vals = self._inventory_redirect(vals)
        if vals.get('active'):
            stock_root, _root = self._inventory_roots()
            if stock_root and stock_root in self:
                # Odoo's Inventory upgrade switches its root back on: keep it archived.
                super(IrUiMenu, stock_root).write(dict(vals, active=False))
                others = self - stock_root
                return super(IrUiMenu, others).write(vals) if others else True
        return super().write(vals)

    @api.model
    def _inventory_take_over_menus(self):
        """Move the menus under Odoo's Inventory root to this app's root and archive it."""
        stock_root, root = self._inventory_roots()
        if not stock_root:
            return
        children = self.with_context(active_test=False).search([('parent_id', '=', stock_root.id)])
        if children:
            super(IrUiMenu, children).write({'parent_id': root.id})
        if stock_root.active:
            super(IrUiMenu, stock_root).write({'active': False})

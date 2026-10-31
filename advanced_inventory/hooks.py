# -*- coding: utf-8 -*-
from odoo import Command

TRANSFER_KEYS = ('edit_all', 'view_all', 'delete_own')
ANALYSIS_KEYS = ('edit_all', 'view_all', 'delete_own')


def post_init_hook(env):
    """Users of Odoo's Inventory groups get the Inventory permissions matching
    what they could do before: Inventory Administrators become Inventory
    Administrators; Inventory Users can create, view and edit every transfer
    and cost analysis, delete their own, validate transfers and apply counts."""
    manager = env.ref('stock.group_stock_manager')
    user = env.ref('stock.group_stock_user')
    admin = env.ref('advanced_inventory.group_inventory_admin')
    admin.user_ids = [Command.link(u.id) for u in manager.user_ids if not u.share]
    officers = user.user_ids.filtered(lambda u: not u.share) - manager.user_ids
    groups = [env.ref('advanced_inventory.group_transfer_%s' % key) for key in TRANSFER_KEYS]
    groups += [env.ref('advanced_inventory.group_cost_analysis_%s' % key) for key in ANALYSIS_KEYS]
    groups += [env.ref('advanced_inventory.group_transfer_validate'),
               env.ref('advanced_inventory.group_adjustment_apply')]
    for group in groups:
        group.user_ids = [Command.link(u.id) for u in officers]
    env['ir.ui.menu']._inventory_take_over_menus()
    # Existing warehouses get a barcode for their label.
    for warehouse in env['stock.warehouse'].with_context(active_test=False).search([('inventory_barcode', '=', False)]):
        code = ''.join(ch for ch in (warehouse.code or str(warehouse.id)) if ch.isalnum()).upper()
        warehouse.inventory_barcode = 'WH-%s' % code


def uninstall_hook(env):
    """Give Odoo's Inventory app its home screen menu back."""
    env = env(context=dict(env.context, inventory_menu_release=True))
    stock_root = env.ref('stock.menu_stock_root', raise_if_not_found=False)
    root = env.ref('advanced_inventory.menu_inventory_root', raise_if_not_found=False)
    if stock_root:
        if root:
            children = env['ir.ui.menu'].with_context(active_test=False).search([
                ('parent_id', '=', root.id), ('id', 'not in', _own_menu_ids(env))])
            children.write({'parent_id': stock_root.id})
        stock_root.write({'active': True})


def _own_menu_ids(env):
    return env['ir.model.data'].search([
        ('module', '=', 'advanced_inventory'), ('model', '=', 'ir.ui.menu')]).mapped('res_id')

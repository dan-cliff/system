# -*- coding: utf-8 -*-
from odoo import Command

PRODUCTION_KEYS = ('edit_all', 'view_all', 'delete_own')
BOM_KEYS = ('edit_all', 'view_all', 'delete_own')
UNBUILD_KEYS = ('edit_all', 'view_all', 'delete_own')


def post_init_hook(env):
    """Users of Odoo's Manufacturing groups get the Manufacturing permissions
    matching what they could do before: Manufacturing Administrators become
    Manufacturing Administrators; Manufacturing Users can create, view and edit
    every order and bill of materials, delete their own and produce. Existing
    work centres get their Work Centre app link."""
    manager = env.ref('mrp.group_mrp_manager')
    user = env.ref('mrp.group_mrp_user')
    admin = env.ref('advanced_manufacturing.group_manufacturing_admin')
    admin.user_ids = [Command.link(u.id) for u in manager.user_ids if not u.share]
    officers = user.user_ids.filtered(lambda u: not u.share) - manager.user_ids
    groups = [env.ref('advanced_manufacturing.group_production_%s' % key) for key in PRODUCTION_KEYS]
    groups += [env.ref('advanced_manufacturing.group_bom_%s' % key) for key in BOM_KEYS]
    groups += [env.ref('advanced_manufacturing.group_unbuild_%s' % key) for key in UNBUILD_KEYS]
    groups.append(env.ref('advanced_manufacturing.group_production_produce'))
    for group in groups:
        group.user_ids = [Command.link(u.id) for u in officers]
    from .models.mrp_workcenter import _new_token
    for workcenter in env['mrp.workcenter'].with_context(active_test=False).search([]):
        if not workcenter.terminal_token:
            workcenter.terminal_token = _new_token()
        if not workcenter.terminal_salt:
            workcenter.terminal_salt = _new_token()


def uninstall_hook(env):
    """Give Odoo's Manufacturing app back its icon and its Work Centers."""
    root = env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
    if root:
        root.write({'name': 'Manufacturing', 'web_icon': 'mrp,static/description/icon.png', 'action': False})
    action = env.ref('mrp.mrp_workcenter_action', raise_if_not_found=False)
    if action:
        action.name = 'Work Centers'
    menu = env.ref('mrp.menu_view_resource_search_mrp', raise_if_not_found=False)
    if menu:
        menu.name = 'Work Centers'
    reporting = env.ref('mrp.menu_mrp_reporting', raise_if_not_found=False)
    if reporting:
        reporting.sequence = 25

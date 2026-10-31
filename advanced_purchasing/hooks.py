# -*- coding: utf-8 -*-
from odoo import Command


def post_init_hook(env):
    """Users of Odoo's Purchase groups get the Purchasing permissions matching
    what they could do before: Purchase Administrators become Purchasing
    Administrators, Purchase Users can create, view and edit every order and
    delete their own."""
    manager = env.ref('purchase.group_purchase_manager')
    user = env.ref('purchase.group_purchase_user')
    admin = env.ref('advanced_purchasing.group_purchasing_admin')
    admin.user_ids = [Command.link(u.id) for u in manager.user_ids if not u.share]
    officer_groups = [env.ref(f'advanced_purchasing.group_purchase_order_{key}')
                      for key in ('edit_all', 'view_all', 'delete_own')]
    officers = user.user_ids.filtered(lambda u: not u.share) - manager.user_ids
    for group in officer_groups:
        group.user_ids = [Command.link(u.id) for u in officers]


def uninstall_hook(env):
    """Give the Purchase app back its name, badge, views and PDF."""
    root = env.ref('purchase.menu_purchase_root', raise_if_not_found=False)
    if root:
        root.write({'name': 'Purchase', 'web_icon': 'purchase,static/description/icon.png'})
    rfq = env.ref('purchase.purchase_rfq', raise_if_not_found=False)
    if rfq:
        rfq.view_mode = 'list,kanban,form,pivot,graph,calendar,activity'
    orders = env.ref('purchase.purchase_form_action', raise_if_not_found=False)
    if orders:
        orders.write({
            'view_mode': 'list,kanban,form,pivot,graph,calendar,activity',
            'view_id': False,
            'view_ids': [Command.clear(),
                         Command.create({'view_mode': 'list', 'view_id': env.ref('purchase.purchase_order_view_tree').id}),
                         Command.create({'view_mode': 'kanban',
                                         'view_id': env.ref('purchase.purchase_order_view_kanban_without_dashboard').id})],
        })
    report = env.ref('purchase.action_report_purchase_order', raise_if_not_found=False)
    if report:
        report.write({'binding_model_id': env['ir.model']._get('purchase.order').id, 'binding_type': 'report'})
    report_main = env.ref('purchase.purchase_report_main', raise_if_not_found=False)
    if report_main:
        report_main.sequence = 99

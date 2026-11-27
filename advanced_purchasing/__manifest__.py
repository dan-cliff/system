# -*- coding: utf-8 -*-
{
    'name': 'Purchasing',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Purchase',
    'sequence': 35,
    'summary': 'Purchase orders with spend levels, manager approvals and a branded PDF Purchase Order',
    'description': """
Purchasing (advanced_purchasing)
================================
A more modern version of Odoo's Purchase app, built on Odoo's own models
(purchase.order, purchase.order.line, ...), so everything that works with
Purchase keeps working (receipts, vendor bills, Advanced Accounts'
remapping, ...). Purchasing takes the Purchase app's place on the home
screen.

* Spend Levels (Configuration › Spend Levels): bands of order value, each
  saying who approves an order in that band - no one, or the 1st, 2nd, 3rd
  or 4th Up Manager. They replace Odoo's single "Purchase Order Approval"
  amount. Levels can be shared by every company or belong to one.
* Approvals: confirming an order works out its Spend Level and approval
  route. Orders that need approval wait in "To Approve" with an activity
  for their approvers, who approve them or send them back with a reason.
  Without Personnel, orders that need approval go to the users with
  Purchase Orders: Approve Any.
* With Personnel (advanced_purchasing_hr, installed automatically): each
  employee has a "Purchases Rules" tab with their spend delegation; orders
  within the buyer's delegation need no approval, and the others go to the
  buyer's 1st to 4th Up Manager (from the org chart) as the Spend Level
  says, escalating past managers whose own delegation is too low.
* Orders open as a list with Purchase's overview cards on top (New, RFQ
  Sent, Late RFQ, Not Acknowledged, Late Receipt, On-Time Delivery, Days to
  Order) plus Estimated Balance Owing: what is still to be paid on
  confirmed orders (their total less what has been paid on their bills).
* PDF Purchase Order: a branded purchase order for the order's company,
  printed straight away (no layout wizard) or emailed to the supplier with
  the PDF attached.
* With Inventory (advanced_purchasing_stock, installed automatically):
  products and variants with their stock on the order lines, receipts, and
  stock levels updated when receipts are validated.
* Permissions per CLAUDE.md: Purchase Orders privileges (Create Only,
  Create and Edit Own / My Team / All, View All, Delete Own / All),
  Approve, Approve Any, Spend Delegations: Manage and the Purchasing
  Administrator. Standard roles ship in advanced_purchasing_permission.
* Lists start with the ID, dates show as dd/mm/yyyy, a Reports menu for
  Report Builder sits before Configuration.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['purchase', 'mail', 'base_setup'],
    'data': [
        'security/advanced_purchasing_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/mail_activity_type_data.xml',
        'data/spend_level_data.xml',
        'report/purchasing_order_report.xml',
        'data/mail_template_data.xml',
        'data/purchasing_titles.xml',
        'wizard/purchasing_reject_wizard_views.xml',
        'views/spend_level_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_purchasing/static/src/purchase_dashboard/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}

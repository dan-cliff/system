# -*- coding: utf-8 -*-
{
    'name': 'Inventory',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'sequence': 30,
    'summary': 'A modern Inventory app: visual warehouse layout, walk-ordered pick and put-away, '
               'product costing, label designer and digital signage',
    'description': """
Inventory (advanced_inventory)
==============================
A more modern version of Odoo's Inventory app, built on Odoo's own models
(stock.warehouse, stock.location, stock.picking, stock.quant, ...), so every
app that works with Inventory (Purchase, Purchasing, Sales, Manufacturing,
Point of Sale, Stocktake, Scanner, ...) keeps working. Odoo's Inventory module
stays installed underneath (the other apps need it), but its home screen
menu is archived: this app's own Inventory menu takes its place, and every
menu other apps put under Odoo's Inventory menu moves here automatically.

* Dashboard: what needs doing today (receipts, picks, put-aways, late and
  waiting transfers) and what the stock is worth: value at cost, potential
  revenue and margin from each product's cost analysis.
* Product costing from the foundations (Product Cost Analysis): each product
  can take its cost from a cost analysis, so stock valuation, margins and
  the Dashboard all use the analysed cost. Analyses refresh their material
  costs from Inventory, show how many units the components on hand can make
  and track break-even progress from what has been delivered.
* Visual warehouse layout: draw each warehouse's rooms, aisles and shelves
  on a floor plan and list every tote. Everything in the designer is a real
  stock location, with its own barcode.
* Walk order: one route through the warehouse numbers every location.
  Picking (products out) and put-away (products into storage) both follow
  it, on screen, on the pick and put-away lists, and in the Scanner app.
  Products are assigned to their storage slots, and receipts put them away
  there automatically.
* Label designer: lay out product, warehouse, room, aisle, shelf and tote
  labels in a visual editor (like Personnel's ID badges), with fields, the
  product picture, the company logo, QR codes and barcodes (Code 128, EAN-13,
  QR) that the Scanner app reads. Each label is on its records' Print menu.
* Digital signage: design signs for warehouses, rooms, aisles, shelves and
  totes in the same visual editor (in pixels), including live stock lists
  and a clock, and show them full screen on any screen through the
  Inventory Signage PWA. With IoT Interfaces (advanced_inventory_iot), a
  Raspberry Pi Node runs the sign with IoT Interfaces' rolling-key security.
* Permissions per CLAUDE.md: Transfers and Cost Analyses privileges (Create
  Only, Create and Edit Own / My Team / All, View All, Delete Own / All),
  Transfers: Validate and Inventory Adjustments: Apply, and the Inventory
  Administrator. Standard roles ship in advanced_inventory_permission.
* Lists start with the ID, dates show as dd/mm/yyyy, a Reports menu for
  Report Builder sits before Configuration.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['stock', 'product_cost_analysis', 'hr', 'mail', 'base_setup'],
    'data': [
        'security/advanced_inventory_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/inventory_data.xml',
        'report/label_report.xml',
        'report/walk_list_report.xml',
        'views/inventory_menus.xml',
        'views/stock_location_views.xml',
        'views/stock_warehouse_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'views/product_slot_views.xml',
        'views/product_views.xml',
        'views/product_cost_analysis_views.xml',
        'views/label_template_views.xml',
        'views/sign_template_views.xml',
        'views/sign_views.xml',
        'views/signage_templates.xml',
        'views/menus.xml',
        'data/inventory_titles.xml',
        'data/design_template_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_inventory/static/src/scss/inventory.scss',
            'advanced_inventory/static/src/designer/**/*',
            'advanced_inventory/static/src/layout_designer/**/*',
            'advanced_inventory/static/src/overview/**/*',
        ],
        'web.assets_tests': [
            'advanced_inventory/static/tests/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}

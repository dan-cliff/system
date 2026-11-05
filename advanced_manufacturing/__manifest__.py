# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing',
    'version': '19.0.1.1.0',
    'category': 'Supply Chain/Manufacturing',
    'sequence': 40,
    'summary': 'A modern Manufacturing app: dashboard, permissions and a Work Centre app '
               'workers sign in to with their ID badge, which keeps working offline',
    'description': """
Manufacturing (advanced_manufacturing)
======================================
A more modern version of Odoo's Manufacturing app, built on Odoo's own models
(mrp.production, mrp.workorder, mrp.bom, mrp.workcenter, ...), so everything
that works with Manufacturing keeps working (Inventory, Purchasing, Sales,
Product Cost Analysis, ...). Manufacturing takes Odoo's Manufacturing app's
place on the home screen, opening on its Dashboard.

* Dashboard: manufacturing orders to confirm, waiting for components, ready,
  in progress, late and produced, and what every work centre is doing (who is
  working, what is waiting, sync issues) with a button to open its app.
* Work Centre app: every work centre has its own link, a Progressive Web App
  that installs on the tablet or computer at the work centre.

  - Workers sign in with their ID badge (camera or an RFID / barcode reader)
    or by selecting their name and entering their PIN, as chosen in
    Manufacturing's Settings: the same ways as On Site's sign in kiosks.
    Operators can be limited per work centre, and the app signs workers out
    after a set time without a tap.
  - They see the work centre's work orders, start, pause and join them (time
    is logged per employee, no user needed), read the operation's
    instructions and components, record the quantity produced and its lot /
    serial number, and finish the work order; finishing the last one can
    produce the manufacturing order (with a backorder for any shortfall).
  - Offline: the app keeps a copy of its workers (hashed badge IDs and PINs)
    and work orders, records work in a queue and syncs it in order when the
    connection returns. Each event is applied once, with the time the worker
    did it. Offline use is limited to the hours set in Settings. What could
    not be synced is shown on the work centre and in the Work Centre App Log.
* Operations get Instructions shown on the Work Centre app.
* Permissions (Permission Management): Manufacturing Orders, Bills of
  Materials and Unbuild Orders each get Create Only, Create and Edit Own / My
  Team / All, View All, Delete Own / All; work orders and time logs follow
  their order, components, by-products and operations their bill of
  materials. Manufacturing Orders: Produce is the workflow privilege, and the
  Manufacturing Administrator has it all. Standard roles ship in
  advanced_manufacturing_permission.
* Lists start with the record ID and dates show as dd/mm/yyyy. Report
  Builder's Reports menu sits before Configuration.

Settings › Manufacturing remaps Odoo's Enterprise options to our apps:

* Barcode Scanner (shown when the Scanner app is installed) installs
  advanced_manufacturing_scanner: a Manufacture tile on the Scanner to scan
  components, record the quantity and lot, and produce.
* Quality installs advanced_manufacturing_checklists: QA checklists from the
  Checklists app, with the QA Checklist Groups chosen right under it.

Add-ons that install automatically: On Site sign in checks
(advanced_manufacturing_attendance) and Actions on manufacturing orders
(advanced_actions_manufacturing).
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mrp', 'advanced_inventory', 'advanced_hr', 'mail', 'base_setup'],
    'data': [
        'security/advanced_manufacturing_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'views/mrp_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/res_config_settings_views.xml',
        'views/terminal_templates.xml',
        'views/menus.xml',
        'data/manufacturing_titles.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_manufacturing/static/src/dashboard/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}

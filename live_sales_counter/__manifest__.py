{
    'name': 'Live Sales Counter',
    'version': '19.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Live, animated sales counter and world map of where buyers are, '
               'across every sales channel, as a private or public web page',
    'description': """
Live Sales Counter
==================
A full-screen web page, like Shopify's Live View, for a TV in the shop or office
or to share with anyone:

* An animated counter of total sales that rolls up as each sale comes in, with
  the number of orders, the average order value and a total per sales channel.
* Every confirmed Sales order (including Website / eCommerce orders and orders
  brought in from other shops) and every paid Point of Sale order is counted.
  Sales orders can be limited to chosen Sales Teams.
* A live animated map (spinning globe or flat world map): every buyer's town
  lights up, and new sales fly in from your shop to the buyer.
* A feed of the latest sales with channel, town and amount.
* Each counter has its own link. Private counters need an Odoo sign in
  with access to the counter; public counters work for anyone with the link
  and never show customer names or addresses (only town and country).
* Access follows the standard permissions (Create Only, Create and Edit
  Own / My Team / All, View All, Delete Own / All); Live Sales Counter -
  Permission Management adds the standard roles.
* Buyers' towns are geocoded in the background with Odoo's geolocation
  provider (Settings > Integrations > Geolocation) and kept under
  Configuration > Buyer Locations.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['sale', 'base_geolocalize', 'hr'],
    'data': [
        'security/live_counter_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/ir_cron_data.xml',
        'views/live_counter_views.xml',
        'views/live_counter_location_views.xml',
        'views/live_counter_menus.xml',
        'views/live_counter_templates.xml',
    ],
    'installable': True,
    'application': True,
}

{
    'name': 'Boarding Kennel Manager - Invoicing',
    'version': '19.0.1.2.0',
    'category': 'Services',
    'summary': 'Invoice kennel bookings in Accounting',
    'description': """
Boarding Kennel Manager - Invoicing
===================================
Installs itself when Boarding Kennel Manager, Accounting and Inventory
are all installed. Switched on per company in Boarding Kennel Manager's
Settings > Integrations > Integrate Bookings with Invoicing, where the
Warehouse/s and Product Categories are chosen.

* Food is picked from inventory: diets and each animal's stay have a
  Food table of items (products in those categories, stocked in those
  warehouses), each with its quantity and frequency, instead of the
  Food Required text. Diets pre-fill the stay's items, and each feed on
  the daily to-do list lists the items due at that time.
* Bookings get a Products tab, offering products from those categories.
* Create Invoice raises a draft invoice: a note with the booking details
  (animals, arrival, departure, nights), then the products. Keepers can
  raise invoices without Accounting access.
* Invoice lines remember the booking product they bill. When products
  are added, changed or removed after invoicing, the booking asks whether
  to raise an amendment invoice with just the changes (removals as
  negative lines, or a credit note when the changes are negative
  overall). No holds the changes until the next change.
* The booking shows its invoices, the amount due and payment status.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['boarding_kennel_manager', 'account', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'security/kennel_invoicing_security.xml',
        'views/res_config_settings_views.xml',
        'views/kennel_booking_views.xml',
        'views/kennel_diet_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}

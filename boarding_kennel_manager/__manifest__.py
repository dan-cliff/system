{
    'name': 'Boarding Kennel Manager',
    'version': '19.0.1.0.0',
    'category': 'Services',
    'summary': 'Manage the dog and cat boarding kennels',
    'description': """
Boarding Kennel Manager
=======================
* Residents: every dog and cat that stays with us, with its Customer
  (a contact), species, breed, sex, desexing, date of birth and age,
  microchip, vet, vaccinations due date, usual diet and standing medical
  and behaviour notes. Customers' contact forms link to their residents.
* Yards: each run, pen or suite with its type, features, the species it
  suits and its capacity.
* Bookings: a customer's arrival and departure date/times and the
  animals they are booking in. Only the selected customer's residents are
  offered. Each animal gets its own line with its yard, diet and the feed
  details (food, quantity, frequency, instructions, owner-supplied food)
  pre-filled from the diet; the details can be changed for the stay, or
  saved as a Custom Diet for that animal to reuse on later stays.
  An animal can't be in two overlapping bookings and a yard can't hold
  more animals at once than its capacity.
* Medical care within each booking: medication to administer (dose,
  route, frequency, times, instructions), a log of every dose given or
  missed, and dated keeper observations. Booking lines warn when an
  animal's vaccinations run out before departure.
* Standard diets under Configuration, plus the choice lists (species,
  sexes, yard types and features, frequencies, medication routes, dose
  outcomes and observation types).
* Multi-company: every record belongs to a company and users only see
  records of the companies they have selected. Diets and choice-list
  options can be left without a company to share them.
* Keepers are ordinary Odoo users given the Boarding Kennel Manager /
  Keeper access level; Administrator adds configuration and deleting
  records.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/kennel_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/kennel_options_data.xml',
        'data/kennel_sequence_data.xml',
        'views/kennel_options_views.xml',
        'views/kennel_diet_views.xml',
        'views/kennel_yard_views.xml',
        'views/kennel_resident_views.xml',
        'views/kennel_medication_views.xml',
        'views/kennel_observation_views.xml',
        'views/kennel_booking_views.xml',
        'views/res_partner_views.xml',
        'wizard/kennel_custom_diet_wizard_views.xml',
        'views/kennel_menus.xml',
    ],
    'installable': True,
    'application': True,
}

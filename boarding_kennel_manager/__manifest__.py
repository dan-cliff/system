{
    'name': 'Boarding Kennel Manager',
    'version': '19.0.1.2.0',
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
  details (food required, frequency, instructions, owner-supplied food)
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
* Daily To-Do list: every checked-in animal's feeds (at its feed
  Frequency's times), medication doses (at the medication Frequency's
  times, between its start and end dates) and observation rounds (at the
  times in Settings) for the day. Keepers open a task, record what was
  eaten / the dose outcome / the observation, add notes and photos and
  press Complete. Completing logs it against the animal: on its chatter
  (with the photos), in its Care Log, and for medication and observations
  in the booking's Medication Log and Observations. Tasks are added on
  check-in and every hour; open ones are dropped on check-out or cancel.
* Customer portal: users with the Customer Portal User permission can
  invite customers from their contact, resident or booking. Customers
  see My Animals and Kennel Bookings in their portal: profiles, stays,
  feeding, medication and doses given, observations, the care log with
  photos, and a chatter to message the keepers.
* Invoicing (Settings > Integrations > Integrate Bookings with
  Invoicing, per company; needs the Accounting and Inventory apps, and
  is provided by Boarding Kennel Manager - Invoicing, which installs
  itself once both are there): bookings get a Products tab (products from
  the chosen Product Categories) and keepers can raise the invoice in
  Accounting: a note with the booking details, then the products. When
  products are added or removed after invoicing, the booking asks
  whether to raise an amendment invoice with just the changes (removals
  as negative lines, or a credit note if the changes are negative
  overall); answering No holds the changes until the next change. The
  booking shows the invoices and their payment status.
* Control Plane: each yard has its own full-screen enclosure display (an
  installable web app, opened from the yard's Control Plane button):
  the yard's name, type and company; its current residents with photo,
  stay, food, medication, medical and behaviour notes (or "Yard
  Vacant"); today's to-do tasks for the yard, completed right there; and
  a toolbar to add Care records (Care Log entry, Medication to Give,
  Medication Dose, Observation) on the screen. It reloads itself after
  the Auto Refresh Interval (minutes idle; 0 turns it off).
* Control Plane settings (for the interactive enclosure screens): theme
  (System, Light or Dark) and background (an image with a transparency
  slider, custom light/dark mode colours, or the company's branding: its
  logo plus the light/dark mode colours).
* Multi-company: every record belongs to a company and users only see
  records of the companies they have selected. Diets and choice-list
  options can be left without a company to share them.
* Keepers are ordinary Odoo users given the Boarding Kennel Manager /
  Keeper access level; Administrator adds configuration and deleting
  records.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['mail', 'portal'],
    'data': [
        'security/kennel_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/kennel_options_data.xml',
        'data/kennel_sequence_data.xml',
        'data/kennel_mail_data.xml',
        'data/kennel_cron_data.xml',
        'views/kennel_options_views.xml',
        'views/kennel_diet_views.xml',
        'views/kennel_yard_views.xml',
        'views/kennel_resident_views.xml',
        'views/kennel_medication_views.xml',
        'views/kennel_observation_views.xml',
        'views/kennel_booking_views.xml',
        'views/kennel_task_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/kennel_portal_templates.xml',
        'views/kennel_control_plane_templates.xml',
        'wizard/kennel_custom_diet_wizard_views.xml',
        'views/kennel_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'boarding_kennel_manager/static/src/percent_slider/*',
        ],
    },
    'installable': True,
    'application': True,
}

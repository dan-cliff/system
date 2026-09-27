{
    'name': 'Zoo Manager',
    'version': '19.0.1.4.0',
    'category': 'Services',
    'summary': 'Manage the wildlife park',
    'description': """
Zoo Manager
===========
* Animal register: every animal with its species, sex, tag/microchip,
  date of birth and age, parents, origin, photo and status (in
  collection, transferred out, deceased).
* Enclosures with capacity; every change of an animal's enclosure is
  logged as a move, building a full location history.
* Classes and species, each with a unique Prefix Code (2 letters for a
  class, 3 for a species) suggested from the name. Species carry the
  regulatory Species Code and whether they are included on the annual
  wildlife return, plus IUCN status and a default diet. Ships with the
  classes and species of the Victorian wildlife schedule (species codes
  and common names), all marked for the annual wildlife return.
* Species scientific classification (kingdom to species), a picture and a
  geographic distribution map. Anything left empty is looked up from the
  scientific name in the background (GBIF for the classification, the
  English Wikipedia article for the pictures); existing values are kept.
  Every night at 3am (the administrator's timezone) any species still
  missing classification fields is looked up again.
* Every night at 4am each species' conservation status is checked against
  the IUCN Red List (via GBIF) and updated if it has changed; new Red List
  categories are added to the Conservation Statuses list. Species have a
  chatter, where every change of conservation status is logged.
* Diets: feed products, quantities and frequency. Settings > Feeds sets
  which warehouses and product categories hold feed; only those products
  are offered on diets and feeding rounds.
* Feeding rounds: plan feeds per enclosure; the food given is filled in
  from the animals' diets. Marking a round Fed takes tracked feed out of
  stock at the chosen warehouse (and resetting puts it back).
* Choice lists (enclosure types, origins, conservation statuses, health
  record types, diet frequencies, food consumption) are managed under
  Configuration.
* Health records: vet visits, vaccinations, treatments and injuries,
  with follow-up dates and activities.
* Weight history per animal, with a graph.
* Keepers are ordinary Odoo users given the Zoo Manager / Keeper
  access level; Zoo Manager / Administrator adds configuration and
  deleting records.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['mail', 'stock'],
    'data': [
        'security/zoo_manager_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/zoo_options_data.xml',
        'data/zoo_manager_sequence.xml',
        'data/zoo_species_data.xml',
        'data/zoo_cron_data.xml',
        'views/zoo_options_views.xml',
        'views/zoo_species_views.xml',
        'views/zoo_diet_views.xml',
        'views/zoo_enclosure_views.xml',
        'views/zoo_animal_views.xml',
        'views/zoo_feeding_views.xml',
        'views/zoo_health_record_views.xml',
        'views/res_config_settings_views.xml',
        'views/zoo_manager_menus.xml',
    ],
    'installable': True,
    'application': True,
}

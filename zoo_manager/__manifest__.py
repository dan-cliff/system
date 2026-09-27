{
    'name': 'Zoo Manager',
    'version': '19.0.1.0.0',
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
* Species (class, IUCN conservation status) and diets (food items,
  quantities and frequency), with a default diet per species.
* Feeding rounds: plan feeds per enclosure, mark them fed and record
  how much was eaten.
* Health records: vet visits, vaccinations, treatments and injuries,
  with follow-up dates and activities.
* Weight history per animal, with a graph.
* Keepers are ordinary Odoo users given the Zoo Manager / Keeper
  access level; Zoo Manager / Administrator adds configuration and
  deleting records.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/zoo_manager_security.xml',
        'security/ir.model.access.csv',
        'data/zoo_manager_sequence.xml',
        'views/zoo_species_views.xml',
        'views/zoo_diet_views.xml',
        'views/zoo_enclosure_views.xml',
        'views/zoo_animal_views.xml',
        'views/zoo_feeding_views.xml',
        'views/zoo_health_record_views.xml',
        'views/zoo_manager_menus.xml',
    ],
    'installable': True,
    'application': True,
}

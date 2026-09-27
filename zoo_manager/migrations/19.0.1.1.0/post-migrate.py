"""Class moved from a selection on zoo.species to the zoo.animal.class model,
and species gained a required Prefix Code.

Odoo keeps the old `animal_class` column when the field is removed, so read it
to create/link the matching classes, then give every species without one a
suggested Prefix Code.
"""
from odoo import SUPERUSER_ID, api

OLD_CLASSES = {
    'mammal': 'Mammals',
    'bird': 'Birds',
    'reptile': 'Reptiles',
    'amphibian': 'Amphibians',
    'fish': 'Fish',
    'invertebrate': 'Invertebrates',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Class = env['zoo.animal.class'].with_context(active_test=False)
    Species = env['zoo.species'].with_context(active_test=False)

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'zoo_species' AND column_name = 'animal_class'
    """)
    if cr.fetchone():
        cr.execute("SELECT id, animal_class FROM zoo_species WHERE animal_class IS NOT NULL AND class_id IS NULL")
        for species_id, old_value in cr.fetchall():
            name = OLD_CLASSES.get(old_value, old_value.title())
            animal_class = Class.search([('name', '=', name)], limit=1) or Class.create({'name': name})
            Species.browse(species_id).class_id = animal_class
        cr.execute("ALTER TABLE zoo_species DROP COLUMN animal_class")
        cr.execute("ALTER TABLE zoo_animal DROP COLUMN IF EXISTS animal_class")

    for species in Species.search([('prefix_code', '=', False)], order='id'):
        species.prefix_code = Species._suggest_prefix_code(species.name)

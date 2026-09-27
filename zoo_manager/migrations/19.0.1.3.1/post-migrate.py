"""Species looked up before 19.0.1.3.1 took GBIF's reptile orders (Squamata,
Testudines, ...) as their class and left Order empty: move them back under
class Reptilia."""
from odoo.addons.zoo_manager.lib.taxonomy_lookup import REPTILE_ORDERS


def migrate(cr, version):
    cr.execute("""
        UPDATE zoo_species
           SET taxon_order = COALESCE(NULLIF(taxon_order, ''), taxon_class),
               taxon_class = 'Reptilia'
         WHERE taxon_class IN %s
    """, [REPTILE_ORDERS])

"""Species common names are no longer unique (the wildlife schedule loaded by
this version lists some twice). Drop the old constraint before the data loads;
Odoo would otherwise only remove it at the end of the upgrade."""


def migrate(cr, version):
    cr.execute("ALTER TABLE zoo_species DROP CONSTRAINT IF EXISTS zoo_species_name_uniq")
    cr.execute("DELETE FROM ir_model_constraint WHERE name = 'zoo_species_name_uniq'")

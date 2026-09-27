"""Upgrade to 19.0.1.3.0.

- Choice lists moved from fixed selections to records under Configuration.
  Odoo keeps the old selection columns, so map each stored value to the
  matching starting record (same key), then drop the old column.
- Diet line "Food" (free text) is now a product: match it by name, otherwise
  keep the text in the line's notes. The free-text "Unit" is now the
  product's unit: keep any old unit that differs in the notes.
- Feeding round "Food Given" (free text) is now food lines; keep the old text
  in the round's notes.
- Show dates as dd/mm/yyyy: the language data only applies on install, so set
  English's date format here for existing databases.
"""
from odoo import SUPERUSER_ID, api

SELECTIONS = [
    # table, old column, new column, xml id prefix
    ('zoo_enclosure', 'enclosure_type', 'enclosure_type_id', 'zoo_enclosure_type'),
    ('zoo_animal', 'origin', 'origin_id', 'zoo_animal_origin'),
    ('zoo_species', 'conservation_status', 'conservation_status_id', 'zoo_conservation_status'),
    ('zoo_health_record', 'record_type', 'record_type_id', 'zoo_health_record_type'),
    ('zoo_diet_line', 'frequency', 'frequency_id', 'zoo_diet_frequency'),
    ('zoo_feeding', 'consumption', 'consumption_id', 'zoo_feeding_consumption'),
]


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _join(*parts, sep=' - '):
    return sep.join(p.strip() for p in parts if p and p.strip())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    lang_en = env.ref('base.lang_en', raise_if_not_found=False)
    if lang_en and lang_en.date_format != '%d/%m/%Y':
        lang_en.date_format = '%d/%m/%Y'

    for table, old, new, prefix in SELECTIONS:
        if not _column_exists(cr, table, old):
            continue
        cr.execute(f'SELECT DISTINCT "{old}" FROM "{table}" WHERE "{old}" IS NOT NULL')
        for (value,) in cr.fetchall():
            record = env.ref(f'zoo_manager.{prefix}_{value}', raise_if_not_found=False)
            if record:
                cr.execute(
                    f'UPDATE "{table}" SET "{new}" = %s WHERE "{old}" = %s AND "{new}" IS NULL',
                    (record.id, value),
                )
        cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{old}"')

    Product = env['product.product'].with_context(active_test=False)
    has_food = _column_exists(cr, 'zoo_diet_line', 'food')
    has_unit = _column_exists(cr, 'zoo_diet_line', 'unit')
    if has_food or has_unit:
        cr.execute('SELECT id, %s, %s FROM zoo_diet_line' % (
            'food' if has_food else 'NULL', 'unit' if has_unit else 'NULL'))
        for line_id, food, unit in cr.fetchall():
            line = env['zoo.diet.line'].browse(line_id)
            keep = []
            if food and not line.product_id:
                product = Product.search([('name', '=ilike', food.strip())], limit=1)
                if product:
                    line.product_id = product
                else:
                    keep.append(food)
            if unit and unit.strip().lower() != (line.product_id.uom_id.name or '').lower():
                keep.append(unit)
            if keep:
                line.notes = _join(' '.join(k.strip() for k in keep), line.notes or '')
        for column in ('food', 'unit'):
            if _column_exists(cr, 'zoo_diet_line', column):
                cr.execute(f'ALTER TABLE zoo_diet_line DROP COLUMN "{column}"')

    for column in ('food_given', 'food_product_id'):
        if not _column_exists(cr, 'zoo_feeding', column):
            continue
        if column == 'food_given':
            cr.execute("SELECT id, food_given FROM zoo_feeding WHERE food_given IS NOT NULL AND food_given != ''")
            for feeding_id, text in cr.fetchall():
                feeding = env['zoo.feeding'].browse(feeding_id)
                feeding.notes = _join(env._('Food given: %s', text.strip()), feeding.notes or '', sep='\n')
        cr.execute(f'ALTER TABLE zoo_feeding DROP COLUMN "{column}"')

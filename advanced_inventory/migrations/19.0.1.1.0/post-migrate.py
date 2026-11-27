# -*- coding: utf-8 -*-
"""Turn the collections' old Year numbers into 1 January of that year."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'advanced_inventory_collection' AND column_name = 'year_number_legacy'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE advanced_inventory_collection
           SET year = make_date(year_number_legacy, 1, 1)
         WHERE year_number_legacy BETWEEN 1900 AND 2999
    """)
    cr.execute('ALTER TABLE advanced_inventory_collection DROP COLUMN year_number_legacy')

# -*- coding: utf-8 -*-
"""Collections' Year changes from a number (2026) to a date (2026-01-01): keep
the numbers aside so post-migrate can turn them into dates."""


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'advanced_inventory_collection' AND column_name = 'year'
    """)
    row = cr.fetchone()
    if row and row[0] == 'integer':
        cr.execute('ALTER TABLE advanced_inventory_collection RENAME COLUMN year TO year_number_legacy')

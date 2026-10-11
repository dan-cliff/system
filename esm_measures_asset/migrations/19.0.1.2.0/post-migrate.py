# -*- coding: utf-8 -*-
"""Templates from before the per-template asset options keep their asset field."""


def migrate(cr, version):
    for code in ('fak', 'eed', 'sma', 'evp'):
        cr.execute(f"UPDATE esm_{code}_template SET esm_asset_enabled = TRUE")

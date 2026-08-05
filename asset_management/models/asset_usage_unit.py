# -*- coding: utf-8 -*-
from odoo import fields, models


class AssetUsageUnit(models.Model):
    _name = 'asset.usage.unit'
    _description = 'Asset Usage Unit'
    _order = 'name'

    name = fields.Char(string='Unit Name', required=True, translate=True,
                       help='e.g. Hours, Kilometres, Cycles, Litres, Tonnes')
    short_code = fields.Char(string='Short Code', size=10,
                             help='Abbreviated unit shown on smart buttons and reports, e.g. hr, km, cyc')
    active = fields.Boolean(default=True)

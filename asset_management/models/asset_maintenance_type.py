# -*- coding: utf-8 -*-
from odoo import fields, models


class AssetMaintenanceType(models.Model):
    _name = 'asset.maintenance.type'
    _description = 'Asset Maintenance Type'
    _order = 'name'

    name = fields.Char(string='Type Name', required=True, translate=True)
    active = fields.Boolean(default=True)

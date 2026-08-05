# -*- coding: utf-8 -*-
from odoo import fields, models


class AssetDefectSeverity(models.Model):
    _name = 'asset.defect.severity'
    _description = 'Asset Defect Severity'
    _order = 'sequence, name'

    name = fields.Char(string='Severity Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

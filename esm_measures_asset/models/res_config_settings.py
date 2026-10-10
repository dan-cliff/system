# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    esm_fak_asset_type_ids = fields.Many2many(
        related='company_id.esm_fak_asset_type_ids', readonly=False,
        string='Visible Asset Types',
        help='Assets with these types will be accessible from the First Aid Kit Inspection.',
    )
    esm_fak_asset_subtype_ids = fields.Many2many(
        related='company_id.esm_fak_asset_subtype_ids', readonly=False,
        string='Visible Asset Subtypes',
        help='Assets with these subtypes will be accessible from the First Aid Kit Inspection.',
    )

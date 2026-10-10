# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    esm_fak_asset_type_ids = fields.Many2many(
        related='company_id.esm_fak_asset_type_ids', readonly=False,
        string='Visible First Aid Kit Asset Types',
        help='Assets with these types will be accessible from the First Aid Kit Inspection.',
    )
    esm_fak_asset_subtype_ids = fields.Many2many(
        related='company_id.esm_fak_asset_subtype_ids', readonly=False,
        string='Visible First Aid Kit Asset Subtypes',
        help='Assets with these subtypes will be accessible from the First Aid Kit Inspection.',
    )

    esm_eed_asset_type_ids = fields.Many2many(
        related='company_id.esm_eed_asset_type_ids', readonly=False,
        string='Visible Emergency Egress Door Asset Types',
        help='Assets with these types will be accessible from the Emergency Egress Door Inspection.',
    )
    esm_eed_asset_subtype_ids = fields.Many2many(
        related='company_id.esm_eed_asset_subtype_ids', readonly=False,
        string='Visible Emergency Egress Door Asset Subtypes',
        help='Assets with these subtypes will be accessible from the Emergency Egress Door Inspection.',
    )

    esm_sma_asset_type_ids = fields.Many2many(
        related='company_id.esm_sma_asset_type_ids', readonly=False,
        string='Visible Smoke Alarm Asset Types',
        help='Assets with these types will be accessible from the Smoke Alarm Inspection.',
    )
    esm_sma_asset_subtype_ids = fields.Many2many(
        related='company_id.esm_sma_asset_subtype_ids', readonly=False,
        string='Visible Smoke Alarm Asset Subtypes',
        help='Assets with these subtypes will be accessible from the Smoke Alarm Inspection.',
    )

    esm_evp_asset_type_ids = fields.Many2many(
        related='company_id.esm_evp_asset_type_ids', readonly=False,
        string='Visible Evacuation Plan Asset Types',
        help='Assets with these types will be accessible from the Evacuation Plan Inspection.',
    )
    esm_evp_asset_subtype_ids = fields.Many2many(
        related='company_id.esm_evp_asset_subtype_ids', readonly=False,
        string='Visible Evacuation Plan Asset Subtypes',
        help='Assets with these subtypes will be accessible from the Evacuation Plan Inspection.',
    )

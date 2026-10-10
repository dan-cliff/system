# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    esm_fak_asset_type_ids = fields.Many2many(
        'asset.type', 'esm_fak_company_asset_type_rel', 'company_id', 'asset_type_id',
        string='First Aid Kit Asset Types',
    )
    esm_fak_asset_subtype_ids = fields.Many2many(
        'asset.subtype', 'esm_fak_company_asset_subtype_rel', 'company_id', 'asset_subtype_id',
        string='First Aid Kit Asset Sub-Types',
    )

    esm_eed_asset_type_ids = fields.Many2many(
        'asset.type', 'esm_eed_company_asset_type_rel', 'company_id', 'asset_type_id',
        string='Emergency Egress Door Asset Types',
    )
    esm_eed_asset_subtype_ids = fields.Many2many(
        'asset.subtype', 'esm_eed_company_asset_subtype_rel', 'company_id', 'asset_subtype_id',
        string='Emergency Egress Door Asset Sub-Types',
    )

    esm_sma_asset_type_ids = fields.Many2many(
        'asset.type', 'esm_sma_company_asset_type_rel', 'company_id', 'asset_type_id',
        string='Smoke Alarm Asset Types',
    )
    esm_sma_asset_subtype_ids = fields.Many2many(
        'asset.subtype', 'esm_sma_company_asset_subtype_rel', 'company_id', 'asset_subtype_id',
        string='Smoke Alarm Asset Sub-Types',
    )

    esm_evp_asset_type_ids = fields.Many2many(
        'asset.type', 'esm_evp_company_asset_type_rel', 'company_id', 'asset_type_id',
        string='Evacuation Plan Asset Types',
    )
    esm_evp_asset_subtype_ids = fields.Many2many(
        'asset.subtype', 'esm_evp_company_asset_subtype_rel', 'company_id', 'asset_subtype_id',
        string='Evacuation Plan Asset Sub-Types',
    )

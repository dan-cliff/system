# -*- coding: utf-8 -*-
from odoo import fields, models


class EsmSmaInspection(models.Model):
    _inherit = 'esm.sma.inspection'
    # The inspection takes its Organisation units from the smoke alarm it inspects.
    _org_parent_field = 'asset_id'

    asset_id = fields.Many2one(
        'asset.asset', string='Smoke Alarm', tracking=True, ondelete='restrict', index=True,
        domain="['|', ('asset_type_id', 'in', esm_sma_asset_type_ids),"
               " ('asset_subtype_id', 'in', esm_sma_asset_subtype_ids)]",
        help='Only assets with the Visible Asset Types or Subtypes chosen in '
             'Settings › ESM Measures are listed.',
    )
    esm_sma_asset_type_ids = fields.Many2many(
        'asset.type', compute='_compute_esm_sma_asset_filter',
    )
    esm_sma_asset_subtype_ids = fields.Many2many(
        'asset.subtype', compute='_compute_esm_sma_asset_filter',
    )

    def _compute_esm_sma_asset_filter(self):
        company = self.env.company
        for inspection in self:
            inspection.esm_sma_asset_type_ids = company.esm_sma_asset_type_ids
            inspection.esm_sma_asset_subtype_ids = company.esm_sma_asset_subtype_ids

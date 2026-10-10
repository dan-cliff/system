# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EsmEedInspection(models.Model):
    _inherit = 'esm.eed.inspection'
    # The inspection takes its Organisation units from the door it inspects.
    _org_parent_field = 'asset_id'

    asset_id = fields.Many2one(
        'asset.asset', string='Emergency Egress Door', tracking=True, ondelete='restrict', index=True,
        domain="['|', ('asset_type_id', 'in', esm_eed_asset_type_ids),"
               " ('asset_subtype_id', 'in', esm_eed_asset_subtype_ids)]",
        help='Only assets with the Visible Asset Types or Subtypes chosen in '
             'Settings › ESM Measures are listed.',
    )
    esm_eed_asset_type_ids = fields.Many2many(
        'asset.type', compute='_compute_esm_eed_asset_filter',
    )
    esm_eed_asset_subtype_ids = fields.Many2many(
        'asset.subtype', compute='_compute_esm_eed_asset_filter',
    )

    @api.depends('company_id')
    def _compute_esm_eed_asset_filter(self):
        # The inspection's company decides which asset types are listed.
        for inspection in self:
            company = inspection.company_id or self.env.company
            inspection.esm_eed_asset_type_ids = company.esm_eed_asset_type_ids
            inspection.esm_eed_asset_subtype_ids = company.esm_eed_asset_subtype_ids

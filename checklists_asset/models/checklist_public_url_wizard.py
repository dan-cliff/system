# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChecklistPublicUrlWizard(models.TransientModel):
    _inherit = 'checklist.public.url.wizard'

    asset_enabled = fields.Boolean(related='template_id.asset_enabled')
    asset_label = fields.Char(related='template_id.asset_label')
    asset_domain = fields.Char(compute='_compute_asset_domain')
    asset_id = fields.Many2one(
        'asset.asset', string='Asset',
        help='Saved as the asset of every checklist submitted with this link.',
    )

    @api.depends('template_id.asset_domain')
    def _compute_asset_domain(self):
        for wizard in self:
            wizard.asset_domain = wizard.template_id.asset_domain or '[]'

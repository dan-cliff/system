# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EsmTemplateMixin(models.AbstractModel):
    """Asset options on every inspection template (all inspection types)."""
    _inherit = 'esm.template.mixin'

    esm_asset_enabled = fields.Boolean(
        string='Asset Integration',
        help='Inspections from this template link to an asset.',
    )
    esm_asset_required = fields.Boolean(
        string='Require Asset',
        help='An asset must be selected on inspections from this template.',
    )
    esm_asset_domain = fields.Char(
        string='Asset Filter', default='[]',
        help='Only assets matching this filter can be selected (on top of the '
             'Visible Asset Types / Subtypes in Settings).',
    )
    esm_asset_label = fields.Char(
        string='Asset Field Label',
        help='Name of the asset field on inspections from this template, '
             'e.g. "Vehicle Kit". Leave empty for the default name.',
    )

    def _export_template_vals(self):
        vals = super()._export_template_vals()
        vals['asset'] = {
            'enabled': self.esm_asset_enabled,
            'required': self.esm_asset_required,
            'domain': self.esm_asset_domain or '[]',
            'label': self.esm_asset_label or '',
        }
        return vals

    @api.model
    def _import_template_vals(self, template):
        vals = super()._import_template_vals(template)
        asset = template.get('asset') or {}
        if asset:
            vals.update({
                'esm_asset_enabled': bool(asset.get('enabled')),
                'esm_asset_required': bool(asset.get('required')),
                'esm_asset_domain': asset.get('domain') or '[]',
                'esm_asset_label': asset.get('label') or False,
            })
        return vals

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChecklistTemplate(models.Model):
    _inherit = 'checklist.template'

    asset_enabled = fields.Boolean(
        string='Asset Selector',
        help="Checklists from this template have an asset field, to record the asset they're for.",
    )
    asset_required = fields.Boolean(
        string='Asset Required',
        help='The asset must be filled in on checklists from this template.',
    )
    asset_domain = fields.Char(
        string='Asset Filter', default='[]',
        help='Only assets matching this filter can be picked on checklists from this template.',
    )
    asset_label = fields.Char(
        string='Asset Selector Label', translate=True,
        help='Name of the asset field on checklists from this template, e.g. "Vehicle". '
             'Leave empty for "Asset".',
    )

    def _export_template_settings(self):
        vals = super()._export_template_settings()
        vals['asset'] = {
            'enabled': self.asset_enabled,
            'required': self.asset_required,
            'filter': self.asset_domain or '[]',
            'label': self.asset_label or '',
        }
        return vals

    @api.model
    def _import_template_settings(self, data):
        vals = super()._import_template_settings(data)
        asset = data.get('asset')
        if isinstance(asset, dict):
            vals.update({
                'asset_enabled': bool(asset.get('enabled')),
                'asset_required': bool(asset.get('required')),
                'asset_domain': asset.get('filter') or '[]',
                'asset_label': asset.get('label') or False,
            })
        return vals

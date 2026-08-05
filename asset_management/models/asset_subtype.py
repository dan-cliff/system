# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetSubtype(models.Model):
    _name = 'asset.subtype'
    _description = 'Asset Sub-Type'
    _order = 'asset_type_id, name'

    name = fields.Char(string='Sub-Type Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    asset_type_id = fields.Many2one(
        'asset.type',
        string='Asset Type',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # ── Usage Unit ────────────────────────────────────────────────────────────
    usage_unit_id = fields.Many2one(
        'asset.usage.unit',
        string='Usage Unit',
        ondelete='set null',
        help='Usage unit for assets of this sub-type. '
             'Automatically inherited from the Asset Type when a type is selected. '
             'Setting this will push the unit down to all assets of this sub-type.',
    )

    # ── Management feature flags ──────────────────────────────────────────────
    has_maintenance = fields.Boolean(
        string='Maintenance',
        help='Enable maintenance scheduling and logging for assets of this sub-type.',
    )
    has_usage_tracking = fields.Boolean(
        string='Usage Tracking',
        help='Enable usage reading logs for assets of this sub-type.',
    )
    has_risk_assessments = fields.Boolean(
        string='Risk Assessments',
        help='Enable risk assessment management for assets of this sub-type.',
    )
    has_hazardous = fields.Boolean(
        string='Hazardous Chemicals & Substances',
        help='Enable hazardous materials tracking for assets of this sub-type.',
    )
    has_project = fields.Boolean(
        string='Project / Job Assignment',
        help='Enable project and job assignment for assets of this sub-type.',
    )
    has_location_tracking = fields.Boolean(
        string='Location Tracking',
        help='Enable GPS location tracking for assets of this sub-type via the Control Plane.',
    )
    has_software = fields.Boolean(
        string='Software Fields',
        help='Enable software details (supplier, website, licence key, notes) for assets of this sub-type.',
    )

    # ── ORM overrides ─────────────────────────────────────────────────────────
    @api.onchange('asset_type_id')
    def _onchange_asset_type_id(self):
        """Inherit the type's usage unit when the type is set/changed."""
        if self.asset_type_id and self.asset_type_id.usage_unit_id:
            self.usage_unit_id = self.asset_type_id.usage_unit_id

    def write(self, vals):
        result = super().write(vals)
        if 'usage_unit_id' in vals:
            unit_id = vals['usage_unit_id']
            for rec in self:
                # Cascade usage unit to all assets belonging to this sub-type
                assets = self.env['asset.asset'].search([
                    ('asset_subtype_id', '=', rec.id),
                ])
                if assets:
                    assets.write({'usage_unit_id': unit_id})
        return result

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetType(models.Model):
    _name = 'asset.type'
    _description = 'Asset Type'
    _order = 'name'

    name = fields.Char(string='Type Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    subtype_ids = fields.One2many('asset.subtype', 'asset_type_id', string='Sub-Types')
    subtype_count = fields.Integer(compute='_compute_subtype_count', string='Sub-Type Count')

    # ── Usage Unit ────────────────────────────────────────────────────────────
    usage_unit_id = fields.Many2one(
        'asset.usage.unit',
        string='Usage Unit',
        ondelete='set null',
        help='Default usage unit for all assets and sub-types of this type. '
             'Setting this will push the unit down to all sub-types and '
             'assets that belong to this type.',
    )

    # ── Management feature flags ──────────────────────────────────────────────
    has_maintenance = fields.Boolean(
        string='Maintenance',
        help='Enable maintenance scheduling and logging for assets of this type.',
    )
    has_usage_tracking = fields.Boolean(
        string='Usage Tracking',
        help='Enable usage reading logs (hours, km, cycles, etc.) for assets of this type.',
    )
    has_risk_assessments = fields.Boolean(
        string='Risk Assessments',
        help='Enable risk assessment management for assets of this type.',
    )
    has_hazardous = fields.Boolean(
        string='Hazardous Chemicals & Substances',
        help='Enable hazardous materials tracking for assets of this type.',
    )
    has_project = fields.Boolean(
        string='Project / Job Assignment',
        help='Enable project and job assignment for assets of this type.',
    )
    has_location_tracking = fields.Boolean(
        string='Location Tracking',
        help='Enable GPS location tracking for assets of this type via the Control Plane.',
    )
    has_software = fields.Boolean(
        string='Software Fields',
        help='Enable software details (supplier, website, licence key, notes) for assets of this type.',
    )

    @api.depends('subtype_ids')
    def _compute_subtype_count(self):
        for rec in self:
            rec.subtype_count = len(rec.subtype_ids)

    # ── ORM overrides ─────────────────────────────────────────────────────────
    def write(self, vals):
        result = super().write(vals)
        if 'usage_unit_id' in vals:
            unit_id = vals['usage_unit_id']
            for rec in self:
                # Push to all sub-types of this type
                if rec.subtype_ids:
                    # Call super directly to avoid recursive propagation into assets
                    # twice — subtype.write() will handle the sub-type → asset cascade
                    rec.subtype_ids.write({'usage_unit_id': unit_id})

                # Push to assets that have this type but NO sub-type
                assets_no_sub = self.env['asset.asset'].search([
                    ('asset_type_id', '=', rec.id),
                    ('asset_subtype_id', '=', False),
                ])
                if assets_no_sub:
                    assets_no_sub.write({'usage_unit_id': unit_id})
        return result

    def action_view_subtypes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Sub-Types',
            'res_model': 'asset.subtype',
            'view_mode': 'list,form',
            'domain': [('asset_type_id', '=', self.id)],
            'context': {'default_asset_type_id': self.id},
        }

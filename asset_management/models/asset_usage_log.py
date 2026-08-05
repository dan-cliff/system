# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetUsageLog(models.Model):
    _name = 'asset.usage.log'
    _description = 'Asset Usage Log'
    _order = 'date desc, id desc'

    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
        domain=[('eff_usage_tracking', '=', True)],
    )
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    source = fields.Selection(
        selection=[
            ('internal', 'Internal'),
            ('control_plane', 'Control Plane (PWA)'),
        ],
        string='Source',
        default='internal',
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Recorded By',
        default=lambda self: self.env.user,
        required=True,
    )
    reading = fields.Float(string='Reading', required=True, digits=(16, 2))
    unit = fields.Char(
        string='Unit',
        compute='_compute_unit',
        store=True,
        help='Derived from the asset\'s Usage Unit.',
    )
    notes = fields.Text(string='Notes')

    # Computed display
    asset_number = fields.Char(related='asset_id.asset_number', store=True)
    asset_type_id = fields.Many2one(related='asset_id.asset_type_id', store=True)

    @api.depends('asset_id.usage_unit_id')
    def _compute_unit(self):
        for rec in self:
            rec.unit = rec.asset_id.usage_unit_id.name or ''

    @api.constrains('reading')
    def _check_reading_positive(self):
        for rec in self:
            if rec.reading < 0:
                raise models.ValidationError('Usage reading must be a positive number.')

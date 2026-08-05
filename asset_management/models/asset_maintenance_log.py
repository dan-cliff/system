# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetMaintenanceLog(models.Model):
    _name = 'asset.maintenance.log'
    _description = 'Asset Maintenance Log'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('asset.maintenance.log') or 'New',
    )
    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(string='Date Performed', required=True, default=fields.Date.context_today)
    date_due = fields.Date(string='Date Due')
    performed_by = fields.Many2one(
        'res.users',
        string='Performed By',
        default=lambda self: self.env.user,
    )
    performed_by_name = fields.Char(
        string='Technician Name',
        help='Name of person who performed the maintenance (used for external/PWA submissions).',
    )
    maintenance_type_id = fields.Many2one(
        'asset.maintenance.type',
        string='Maintenance Type',
        ondelete='set null',
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True)],
        ondelete='set null',
    )
    description = fields.Text(string='Work Performed', required=True)
    parts_used = fields.Text(string='Parts / Materials Used')
    cost = fields.Float(string='Cost', digits=(16, 2))
    next_due_date = fields.Date(string='Next Due Date')
    next_due_reading = fields.Float(string='Next Due Reading', digits=(16, 2))

    # Source tracking
    source = fields.Selection(
        selection=[
            ('internal', 'Internal'),
            ('control_plane', 'Control Plane (PWA)'),
        ],
        string='Source',
        default='internal',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.maintenance.log') or 'New'
        return super().create(vals_list)

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetDefect(models.Model):
    _name = 'asset.defect'
    _description = 'Asset Defect Report'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('asset.defect') or 'New',
    )
    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    date = fields.Date(string='Reported Date', required=True, default=fields.Date.context_today)
    date_due = fields.Date(string='Due Date')
    reported_by = fields.Many2one(
        'res.users',
        string='Reported By',
        default=lambda self: self.env.user,
    )
    reported_by_name = fields.Char(
        string='Reporter Name',
        help='Name of person who reported the defect (used for external/PWA submissions).',
    )
    description = fields.Text(string='Description', required=True)
    severity_id = fields.Many2one(
        'asset.defect.severity',
        string='Severity',
        ondelete='set null',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('in_progress', 'In Progress'),
            ('resolved', 'Resolved'),
        ],
        string='Status',
        default='open',
        required=True,
        tracking=True,
    )
    resolved_date = fields.Date(string='Resolved Date')
    resolution_notes = fields.Text(string='Resolution Notes')

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
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.defect') or 'New'
        return super().create(vals_list)

    def action_in_progress(self):
        self.state = 'in_progress'

    def action_resolve(self):
        self.state = 'resolved'
        if not self.resolved_date:
            self.resolved_date = fields.Date.today()

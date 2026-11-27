# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mrp_terminal_identify_badge = fields.Boolean(related='company_id.mrp_terminal_identify_badge', readonly=False)
    mrp_terminal_identify_reader = fields.Boolean(related='company_id.mrp_terminal_identify_reader', readonly=False)
    mrp_terminal_identify_name = fields.Boolean(related='company_id.mrp_terminal_identify_name', readonly=False)
    mrp_terminal_require_pin = fields.Boolean(related='company_id.mrp_terminal_require_pin', readonly=False)
    mrp_terminal_idle_minutes = fields.Integer(related='company_id.mrp_terminal_idle_minutes', readonly=False)
    mrp_terminal_offline = fields.Boolean(related='company_id.mrp_terminal_offline', readonly=False)
    mrp_terminal_offline_hours = fields.Integer(related='company_id.mrp_terminal_offline_hours', readonly=False)
    mrp_terminal_refresh_minutes = fields.Integer(related='company_id.mrp_terminal_refresh_minutes', readonly=False)
    mrp_terminal_close_production = fields.Boolean(related='company_id.mrp_terminal_close_production', readonly=False)

    # Odoo's Barcode Scanner and Quality settings, remapped to our apps.
    module_advanced_manufacturing_scanner = fields.Boolean(
        string='Barcode Scanner',
        help='Produce manufacturing orders from the Scanner app (installs Manufacturing - Scanner).',
    )
    mrp_scanner_app_installed = fields.Boolean(compute='_compute_mrp_scanner_app_installed')
    module_advanced_manufacturing_checklists = fields.Boolean(
        string='Quality',
        help='QA checklists (Checklists app) for manufacturing orders and work centres '
             '(installs Manufacturing - Checklists).',
    )

    @api.depends('company_id')
    def _compute_mrp_scanner_app_installed(self):
        installed = bool(self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'scanner_app'), ('state', '=', 'installed')]))
        for settings in self:
            settings.mrp_scanner_app_installed = installed

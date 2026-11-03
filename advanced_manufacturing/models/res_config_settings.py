# -*- coding: utf-8 -*-
from odoo import fields, models


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

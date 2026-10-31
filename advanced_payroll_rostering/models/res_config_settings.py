# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payroll_hours_source = fields.Selection(selection_add=[('roster', 'Published Roster and Approved Leave')])

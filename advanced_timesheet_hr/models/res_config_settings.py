# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advanced_timesheet_manager_approval = fields.Boolean(
        string='Manager Approval', config_parameter='advanced_timesheet.manager_approval',
        help='Submitted timesheets wait for the employee\'s Manager to approve them.',
    )

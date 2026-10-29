# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advanced_timesheet_manager_approval = fields.Boolean(
        string='Manager Approval', config_parameter='advanced_timesheet.manager_approval',
        help='Submitted timesheets wait for the employee\'s Manager to approve them.',
    )
    # Shown by the bridges that fill timesheets from attendances
    # (advanced_timesheet_attendance, advanced_timesheet_onsite).
    advanced_timesheet_attendance_sync = fields.Boolean(
        string='Fill from Attendances', config_parameter='advanced_timesheet.attendance_sync',
        help='Every finished attendance becomes an automatic entry on the employee\'s timesheet. '
             'Manual entries are still allowed.',
    )


# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advanced_timesheet_attendance_sync = fields.Boolean(
        string='Fill from Attendances', config_parameter='advanced_timesheet.attendance_sync',
        help='Every finished attendance becomes an automatic entry on the employee\'s timesheet. '
             'Manual entries are still allowed.',
    )

    def set_values(self):
        was_enabled = self.env['hr.attendance']._advanced_timesheet_sync_enabled()
        super().set_values()
        if self.advanced_timesheet_attendance_sync and not was_enabled:
            self.env['hr.attendance']._advanced_timesheet_sync_missing()

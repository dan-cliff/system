# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advanced_timesheet_attendance_superseded = fields.Boolean(
        compute='_compute_advanced_timesheet_attendance_superseded',
    )

    def _compute_advanced_timesheet_attendance_superseded(self):
        self.advanced_timesheet_attendance_superseded = self.env['hr.attendance']._advanced_timesheet_superseded()

    def set_values(self):
        Attendance = self.env['hr.attendance']
        was_enabled = Attendance._advanced_timesheet_sync_enabled()
        super().set_values()
        if not was_enabled and Attendance._advanced_timesheet_sync_enabled():
            Attendance._advanced_timesheet_sync_missing()

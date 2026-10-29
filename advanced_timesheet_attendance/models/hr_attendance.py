# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrAttendance(models.Model):
    _name = 'hr.attendance'
    _inherit = ['hr.attendance', 'advanced.timesheet.attendance.mixin']

    advanced_timesheet_line_ids = fields.One2many(
        'advanced.timesheet.line', 'attendance_id', string='Timesheet Entries', readonly=True,
    )

    @api.model
    def _advanced_timesheet_superseded(self):
        """On Site's bridge (advanced_timesheet_onsite) fills timesheets from On Site's
        attendances instead, which On Site copies from these."""
        return 'onsite_attendance_id' in self.env['advanced.timesheet.line']._fields

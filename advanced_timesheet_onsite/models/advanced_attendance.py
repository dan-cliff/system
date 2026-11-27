# -*- coding: utf-8 -*-
from odoo import fields, models


class AdvancedAttendance(models.Model):
    _name = 'advanced.attendance'
    _inherit = ['advanced.attendance', 'advanced.timesheet.attendance.mixin']

    advanced_timesheet_line_ids = fields.One2many(
        'advanced.timesheet.line', 'onsite_attendance_id', string='Timesheet Entries', readonly=True,
    )

    def _advanced_timesheet_tz(self):
        self.ensure_one()
        return self.employee_id._get_tz()

    def _advanced_timesheet_local_date(self):
        # On Site's own day of the attendance (the day signed in, in the employee's time zone).
        self.ensure_one()
        return self.date or super()._advanced_timesheet_local_date()

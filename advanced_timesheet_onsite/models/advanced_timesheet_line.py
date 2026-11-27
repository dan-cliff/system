# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AdvancedTimesheetLine(models.Model):
    _inherit = 'advanced.timesheet.line'

    onsite_attendance_id = fields.Many2one(
        'advanced.attendance', string='On Site Attendance', index='btree_not_null', readonly=True,
        copy=False, ondelete='cascade',
    )

    _onsite_attendance_uniq = models.Constraint(
        'UNIQUE(onsite_attendance_id)', 'An attendance can only be on one timesheet entry.',
    )

    def _grid_auto_label(self):
        if self.onsite_attendance_id:
            return _('Attendance')
        return super()._grid_auto_label()

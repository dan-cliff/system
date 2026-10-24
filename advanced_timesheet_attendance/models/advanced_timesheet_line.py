# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AdvancedTimesheetLine(models.Model):
    _inherit = 'advanced.timesheet.line'

    attendance_id = fields.Many2one(
        'hr.attendance', string='Attendance', index='btree_not_null', readonly=True, copy=False,
        ondelete='cascade',
    )

    _attendance_uniq = models.Constraint(
        'UNIQUE(attendance_id)', 'An attendance can only be on one timesheet entry.',
    )

    def _grid_auto_label(self):
        if self.attendance_id:
            return _('Attendance')
        return super()._grid_auto_label()

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models

# How early before the shift a sign in still counts towards it.
EARLY_SIGN_IN = timedelta(hours=2)

STATUS_BADGES = {
    'in_progress': 'text-bg-info',
    'attended': 'text-bg-success',
    'late': 'text-bg-warning',
    'absent': 'text-bg-danger',
}


class RosteringShift(models.Model):
    _inherit = 'rostering.shift'

    attendance_check_in = fields.Datetime(string='Signed In', compute='_compute_attendance')
    attendance_check_out = fields.Datetime(string='Signed Out', compute='_compute_attendance')
    attended_hours = fields.Float(string='Hours On Site', compute='_compute_attendance')
    late_minutes = fields.Integer(string='Minutes Late', compute='_compute_attendance')
    # Worked out on the fly from the roster and On Site; not a choice list.
    attendance_status = fields.Selection(
        [('upcoming', 'Upcoming'), ('in_progress', 'Signed In'), ('attended', 'Attended'),
         ('late', 'Late'), ('absent', 'Absent'), ('on_leave', 'On Leave'), ('unassigned', 'Unassigned')],
        string='Attendance', compute='_compute_attendance',
    )

    @api.depends('employee_id', 'start_datetime', 'end_datetime')
    @api.depends_context('uid')
    def _compute_attendance(self):
        now = fields.Datetime.now()
        try:
            grace = timedelta(minutes=int(self.env['ir.config_parameter'].sudo().get_param(
                'advanced_rostering.late_grace_minutes', 5)))
        except ValueError:
            grace = timedelta(minutes=5)
        shifts = self.filtered(lambda s: s.employee_id and s.start_datetime and s.end_datetime)
        attendances = self.env['advanced.attendance'].sudo()
        if shifts:
            attendances = attendances.search([
                ('employee_id', 'in', shifts.employee_id.ids),
                ('check_in', '<', max(shifts.mapped('end_datetime'))),
                ('check_in', '>=', min(shifts.mapped('start_datetime')) - EARLY_SIGN_IN - timedelta(days=1)),
            ], order='check_in')
        by_employee = attendances.grouped('employee_id')
        for shift in self:
            shift.attendance_check_in = shift.attendance_check_out = False
            shift.attended_hours = 0.0
            shift.late_minutes = 0
            if not shift.employee_id:
                shift.attendance_status = 'unassigned'
                continue
            if shift not in shifts:
                shift.attendance_status = 'upcoming'
                continue
            start, end = shift.start_datetime, shift.end_datetime
            matching = [
                att for att in by_employee.get(shift.employee_id, [])
                if att.check_in < end and (att.check_out or now) > start - EARLY_SIGN_IN
            ]
            if matching:
                first_in = matching[0].check_in
                shift.attendance_check_in = first_in
                shift.attendance_check_out = False if any(not att.check_out for att in matching) \
                    else max(att.check_out for att in matching)
                shift.attended_hours = sum(att.worked_hours for att in matching)
                late = first_in - start
                if late > grace:
                    shift.late_minutes = int(late.total_seconds() // 60)
                if shift.on_leave:
                    shift.attendance_status = 'on_leave'
                elif not shift.attendance_check_out and now < end:
                    shift.attendance_status = 'late' if shift.late_minutes else 'in_progress'
                else:
                    shift.attendance_status = 'late' if shift.late_minutes else 'attended'
            elif shift.on_leave:
                shift.attendance_status = 'on_leave'
            elif now < start + grace:
                shift.attendance_status = 'upcoming'
            else:
                shift.attendance_status = 'absent'

    def _my_roster_values(self):
        values = super()._my_roster_values()
        if self.attendance_status in STATUS_BADGES:
            label = dict(self._fields['attendance_status']._description_selection(self.env))[self.attendance_status]
            if self.attendance_status == 'late':
                label = _('%(status)s (%(minutes)s min)', status=label, minutes=self.late_minutes)
            values['extra'].append({'label': label, 'class': STATUS_BADGES[self.attendance_status]})
        return values

from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.intervals import Intervals


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Prefixed with onsite_ so they never clash with Odoo's Attendances app
    # while both are installed.
    onsite_attendance_ids = fields.One2many(
        'advanced.attendance', 'employee_id', string='On Site Attendances',
        groups='advanced_attendance.group_onsite_user',
    )
    onsite_last_attendance_id = fields.Many2one(
        'advanced.attendance', string='Last On Site Attendance', compute='_compute_onsite_last_attendance_id',
        store=True, groups='advanced_attendance.group_onsite_user',
    )
    onsite_last_check_in = fields.Datetime(
        string='Last Signed In', related='onsite_last_attendance_id.check_in', store=True,
        groups='advanced_attendance.group_onsite_user',
    )
    onsite_last_check_out = fields.Datetime(
        string='Last Signed Out', related='onsite_last_attendance_id.check_out', store=True,
        groups='advanced_attendance.group_onsite_user',
    )
    onsite_state = fields.Selection(
        [('checked_out', 'Signed Out'), ('checked_in', 'Signed In')],
        string='On Site Status', compute='_compute_onsite_state',
        groups='advanced_attendance.group_onsite_user',
    )
    onsite_overtime_ids = fields.One2many(
        'advanced.attendance.overtime.line', 'employee_id', string='Extra Hours',
        groups='advanced_attendance.group_onsite_user',
    )
    onsite_total_overtime = fields.Float(
        string='Approved Extra Hours', compute='_compute_onsite_total_overtime',
        groups='advanced_attendance.group_onsite_user',
        help='Approved extra hours, less missed hours, over all time.',
    )
    onsite_ruleset_id = fields.Many2one(
        related='version_id.onsite_ruleset_id', readonly=False, inherited=True,
        groups='advanced_attendance.group_onsite_admin',
    )
    onsite_display_overtime = fields.Boolean(related='company_id.onsite_display_overtime')
    onsite_hours_today = fields.Float(
        string='Hours On Site Today', compute='_compute_onsite_hours_today',
        groups='advanced_attendance.group_onsite_user',
    )

    @api.depends('onsite_attendance_ids.check_in')
    def _compute_onsite_last_attendance_id(self):
        Attendance = self.env['advanced.attendance'].sudo()
        now = fields.Datetime.now()
        for employee in self:
            employee.onsite_last_attendance_id = Attendance.search([
                ('employee_id', '=', employee.id), ('check_in', '<=', now),
            ], order='check_in desc', limit=1) if employee.id else False

    @api.depends('onsite_last_attendance_id.check_out')
    def _compute_onsite_state(self):
        for employee in self:
            attendance = employee.sudo().onsite_last_attendance_id
            employee.onsite_state = 'checked_in' if attendance and not attendance.check_out else 'checked_out'

    @api.depends('onsite_overtime_ids.manual_duration', 'onsite_overtime_ids.status')
    def _compute_onsite_total_overtime(self):
        totals = dict(self.env['advanced.attendance.overtime.line'].sudo()._read_group(
            [('status', '=', 'approved'), ('employee_id', 'in', self.ids)],
            ['employee_id'], ['manual_duration:sum'],
        ))
        for employee in self:
            employee.onsite_total_overtime = totals.get(employee, 0)

    def action_archive(self):
        result = super().action_archive()
        # Archived employees are no longer on site.
        self.env['advanced.attendance'].sudo().search([
            ('employee_id', 'in', self.ids), ('check_out', '=', False),
        ]).write({'check_out': fields.Datetime.now()})
        return result

    def _compute_onsite_hours_today(self):
        now = fields.Datetime.now()
        Attendance = self.env['advanced.attendance'].sudo()
        for employee in self:
            tz = pytz.timezone(employee._get_tz() or 'UTC')
            day_start = tz.localize(datetime.combine(pytz.utc.localize(now).astimezone(tz).date(), time.min))
            start = day_start.astimezone(pytz.utc).replace(tzinfo=None)
            hours = 0.0
            for attendance in Attendance.search([
                ('employee_id', '=', employee.id), ('check_in', '<=', now),
                '|', ('check_out', '>=', start), ('check_out', '=', False),
            ]):
                hours += ((attendance.check_out or now) - max(attendance.check_in, start)).total_seconds() / 3600
            employee.onsite_hours_today = hours

    # Show employees who are signed in as present (Odoo's Attendances app does the
    # same with its own records).
    @api.depends('onsite_last_attendance_id.check_out')
    def _compute_presence_state(self):
        super()._compute_presence_state()
        signed_in = set(self.env['advanced.attendance'].sudo().search([
            ('employee_id', 'in', self.ids), ('check_out', '=', False),
        ]).employee_id.ids)
        for employee in self:
            if employee.id in signed_in and employee.hr_presence_state != 'archive':
                employee.hr_presence_state = 'present'

    # ── Learning capabilities (kiosk sign in rules) ────────────────────────
    def _onsite_current_capabilities(self, courses=None):
        """Return the Learning capabilities each employee currently holds.

        A capability is current when the employee has a completed training
        record for the course that has not expired.

        :param courses: optional ``lms.course`` recordset to limit the check to
        :return: ``{employee_id: {course_id: expiry_date or False}}`` where
            ``False`` means the capability never expires. When an employee
            holds several current records for a course, the latest expiry wins.
        """
        result = {employee.id: {} for employee in self}
        if not self:
            return result
        today = fields.Date.context_today(self)
        domain = [
            ('employee_id', 'in', self.ids),
            ('state', '=', 'completed'),
            '|', ('expiry_date', '=', False), ('expiry_date', '>=', today),
        ]
        if courses is not None:
            if not courses:
                return result
            domain.append(('course_id', 'in', courses.ids))
        records = self.env['lms.employee.record'].sudo().search_read(
            domain, ['employee_id', 'course_id', 'expiry_date'],
        )
        for rec in records:
            held = result[rec['employee_id'][0]]
            course_id = rec['course_id'][0]
            expiry = rec['expiry_date']
            if course_id not in held:
                held[course_id] = expiry
            elif held[course_id] and (not expiry or expiry > held[course_id]):
                held[course_id] = expiry
        return result

    # ── Signing in and out from Odoo (toolbar) ─────────────────────────────
    def _onsite_systray_data(self):
        """What the toolbar Sign In / Out button shows for this employee."""
        self.ensure_one()
        employee = self.sudo()
        last = employee.onsite_last_attendance_id
        company = employee.company_id
        return {
            'id': employee.id,
            'name': employee.name,
            'state': employee.onsite_state,
            'hours_today': employee.onsite_hours_today,
            'last_check_in': fields.Datetime.to_string(last.check_in) if last else False,
            'location_tracking': company.onsite_location_tracking,
        }

    def _onsite_sign_in_out(self, where=None):
        """Sign the employee in, or out when they are signed in.

        :param where: optional ``{'latitude', 'longitude', 'location', 'ip_address', 'browser'}``
        :return: the attendance
        """
        self.ensure_one()
        Attendance = self.env['advanced.attendance'].sudo()
        employee = self.sudo()
        now = fields.Datetime.now()
        where = where or {}
        attendance = Attendance.search([('employee_id', '=', employee.id), ('check_out', '=', False)],
                                       order='check_in desc', limit=1)
        if attendance:
            due = attendance._auto_sign_out_due()
            if due and due <= now:
                # Overdue automatic sign out: apply it, then sign them in again.
                if attendance.in_kiosk_id:
                    attendance.in_kiosk_id._kiosk_apply_auto_sign_out(attendance, due)
                else:
                    attendance._apply_auto_sign_out(due)
                attendance = Attendance
        if not attendance:
            return Attendance.create({
                'employee_id': employee.id,
                'check_in': now,
                'in_mode': 'systray',
                **{f'in_{key}': value for key, value in where.items()},
            })
        if attendance.in_kiosk_id and attendance.in_kiosk_id.other_sign_out_action == 'block':
            raise UserError(_('You signed in at %s, so you must sign out there.', attendance.in_kiosk_id.name))
        attendance.write({
            'check_out': max(now, attendance.check_in),
            'out_mode': 'systray',
            **{f'out_{key}': value for key, value in where.items()},
        })
        return attendance

    # ── Working schedules for the overtime rules (from Odoo's Attendances app) ──
    def _get_schedules_by_employee_by_work_type(self, start, stop, version_periods_by_employee):
        employees_by_calendar = defaultdict(lambda: self.env['hr.employee'])
        leave_intervals_by_cal_by_resource = defaultdict(lambda: defaultdict(Intervals))
        attendance_intervals_by_cal = defaultdict(Intervals)
        lunch_intervals_by_cal = defaultdict(Intervals)

        def naive(intervals):
            return Intervals([(i_start.replace(tzinfo=None), i_stop.replace(tzinfo=None), i_model)
                              for (i_start, i_stop, i_model) in intervals])

        for employee, intervals in version_periods_by_employee.items():
            for (_start, _stop, version) in intervals:
                employees_by_calendar[version.resource_calendar_id] |= employee

        for cal, employees in employees_by_calendar.items():
            if not cal:  # employees are fully flexible
                continue
            for resource, leave_intervals in cal._leave_intervals_batch(start, stop, resources=employees.resource_id).items():
                leave_intervals_by_cal_by_resource[cal][resource] = naive(leave_intervals)
            attendance_intervals_by_cal[cal] = naive(cal._attendance_intervals_batch(start, stop)[False])
            lunch_intervals_by_cal[cal] = naive(cal._attendance_intervals_batch(start, stop, lunch=True)[False])

        full_schedule_by_employee = {
            'leave': defaultdict(Intervals),
            'schedule': defaultdict(lambda: {'work': Intervals([]), 'lunch': Intervals([])}),
            'fully_flexible': defaultdict(Intervals),
        }
        for employee, intervals in version_periods_by_employee.items():
            for (p_start, p_stop, version) in intervals:
                interval = Intervals([(p_start.replace(tzinfo=None), p_stop.replace(tzinfo=None), self.env['resource.calendar'])])
                calendar = version.resource_calendar_id
                if not calendar:
                    full_schedule_by_employee['fully_flexible'][employee] |= interval
                    continue
                full_schedule_by_employee['leave'][employee] |= (
                    leave_intervals_by_cal_by_resource[calendar][employee.resource_id.id] & interval)
                full_schedule_by_employee['schedule'][employee]['work'] |= attendance_intervals_by_cal[calendar] & interval
                full_schedule_by_employee['schedule'][employee]['lunch'] |= lunch_intervals_by_cal[calendar] & interval
        return full_schedule_by_employee

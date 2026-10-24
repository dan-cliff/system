# -*- coding: utf-8 -*-
import pytz

from odoo import _, api, fields, models
from odoo.tools import format_time

# Attendance fields that change the timesheet entry.
SYNC_FIELDS = {'employee_id', 'check_in', 'check_out', 'worked_hours'}


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    advanced_timesheet_line_ids = fields.One2many(
        'advanced.timesheet.line', 'attendance_id', string='Timesheet Entries', readonly=True,
    )

    @api.model
    def _advanced_timesheet_sync_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('advanced_timesheet.attendance_sync') == 'True'

    @api.model_create_multi
    def create(self, vals_list):
        attendances = super().create(vals_list)
        if self._advanced_timesheet_sync_enabled():
            attendances._advanced_timesheet_sync()
        return attendances

    def write(self, vals):
        res = super().write(vals)
        if SYNC_FIELDS & set(vals) and self._advanced_timesheet_sync_enabled():
            self._advanced_timesheet_sync()
        return res

    def unlink(self):
        self.advanced_timesheet_line_ids.sudo().with_context(advanced_timesheet_sync=True).unlink()
        return super().unlink()

    def _advanced_timesheet_local_date(self):
        """The day the attendance started, in the employee's time zone."""
        self.ensure_one()
        tz = pytz.timezone(self.employee_id.tz or self.env.user.tz or 'UTC')
        return pytz.utc.localize(self.check_in).astimezone(tz).date()

    def _advanced_timesheet_description(self):
        self.ensure_one()
        tz = self.employee_id.tz or self.env.user.tz or 'UTC'
        return _('Attendance %(check_in)s – %(check_out)s',
                 check_in=format_time(self.env, self.check_in, tz=tz, time_format='HH:mm'),
                 check_out=format_time(self.env, self.check_out, tz=tz, time_format='HH:mm'))

    def _advanced_timesheet_sync(self):
        """Make each attendance's timesheet entry match it: finished attendances
        (checked out) get an automatic entry on the employee's timesheet for
        that day; open ones have none."""
        Sheet = self.env['advanced.timesheet'].sudo().with_context(advanced_timesheet_sync=True)
        Line = self.env['advanced.timesheet.line'].sudo().with_context(advanced_timesheet_sync=True)
        for attendance in self.sudo().with_context(advanced_timesheet_sync=True):
            line = attendance.advanced_timesheet_line_ids[:1]
            if not attendance.check_out or not attendance.employee_id:
                line.unlink()
                continue
            day = attendance._advanced_timesheet_local_date()
            sheet = line.sheet_id
            if not sheet or not sheet.date_start <= day <= sheet.date_end or sheet.employee_id != attendance.employee_id:
                sheet = Sheet.with_company(attendance.employee_id.company_id)._get_or_create_for(
                    day, {'employee_id': attendance.employee_id.id})
            vals = {
                'sheet_id': sheet.id,
                'date': day,
                'unit_amount': attendance.worked_hours,
                'is_auto': True,
            }
            if line:
                changed = {key: value for key, value in vals.items()
                           if (line[key].id if key == 'sheet_id' else line[key]) != value}
                if changed:
                    line.write(changed)
            else:
                line = Line.create(dict(vals, attendance_id=attendance.id,
                                        name=attendance._advanced_timesheet_description()))
                if sheet.state != 'draft':
                    sheet.message_post(body=_('Attendance on %s added after the timesheet was submitted.',
                                              day.strftime('%d/%m/%Y')))

    @api.model
    def _advanced_timesheet_sync_missing(self):
        """Fill in every finished attendance that has no timesheet entry yet."""
        attendances = self.sudo().search([
            ('check_out', '!=', False),
            ('advanced_timesheet_line_ids', '=', False),
        ])
        attendances._advanced_timesheet_sync()
        return attendances

    @api.model
    def _cron_advanced_timesheet_sync(self):
        if self._advanced_timesheet_sync_enabled():
            self._advanced_timesheet_sync_missing()

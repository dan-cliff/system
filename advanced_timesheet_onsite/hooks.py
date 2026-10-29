# -*- coding: utf-8 -*-
"""Move timesheet entries between the two attendance bridges.

On Site copies Odoo's attendances (hr.attendance) into its own when it is
installed. While "Advanced Timesheets - Attendances" is installed too, this
module takes over its entries: each moves to the On Site attendance with the
same employee and sign in time (keeping its work type, project, task and
description), and that module stops filling timesheets. Uninstalling this
module hands them back.
"""
import logging

_logger = logging.getLogger(__name__)


def _lines(env):
    return env['advanced.timesheet.line'].sudo().with_context(advanced_timesheet_sync=True, active_test=False)


def _attendance_keys(records):
    return {(record.employee_id.id, record.check_in): record.id for record in records}


def post_init_hook(env):
    Line = _lines(env)
    Attendance = env['advanced.attendance'].sudo().with_context(active_test=False)
    if 'attendance_id' in Line._fields:
        lines = Line.search([('attendance_id', '!=', False)])
        onsite = _attendance_keys(Attendance.search([
            ('employee_id', 'in', lines.attendance_id.employee_id.ids),
            ('advanced_timesheet_line_ids', '=', False),
        ]))
        taken = Line.browse()
        for line in lines:
            old = line.attendance_id
            new_id = onsite.pop((old.employee_id.id, old.check_in), False)
            if new_id:
                line.write({'onsite_attendance_id': new_id, 'attendance_id': False})
                taken |= line
            else:
                # No On Site copy: keep the hours as an ordinary entry.
                line.write({'attendance_id': False, 'is_auto': False})
        _logger.info('Advanced Timesheets - On Site: took over %s attendance entries (%s kept as manual entries)',
                     len(taken), len(lines - taken))
        if Attendance._advanced_timesheet_sync_enabled():
            taken.onsite_attendance_id._advanced_timesheet_sync()
    if Attendance._advanced_timesheet_sync_enabled():
        Attendance._advanced_timesheet_sync_missing()


def uninstall_hook(env):
    Line = _lines(env)
    lines = Line.search([('onsite_attendance_id', '!=', False)])
    if not lines:
        return
    if 'attendance_id' in Line._fields:
        olds = env['hr.attendance'].sudo().search([
            ('employee_id', 'in', lines.onsite_attendance_id.employee_id.ids),
            ('advanced_timesheet_line_ids', '=', False),
        ])
        hr_keys = _attendance_keys(olds)
    else:
        hr_keys = {}
    for line in lines:
        new = line.onsite_attendance_id
        old_id = hr_keys.pop((new.employee_id.id, new.check_in), False)
        if old_id:
            line.write({'attendance_id': old_id, 'onsite_attendance_id': False})
        else:
            # Nothing fills it any more: keep the hours as an ordinary entry.
            line.write({'onsite_attendance_id': False, 'is_auto': False})

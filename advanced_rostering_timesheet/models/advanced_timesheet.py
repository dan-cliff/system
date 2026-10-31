# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvancedTimesheetLine(models.Model):
    _inherit = 'advanced.timesheet.line'

    rostering_shift_id = fields.Many2one('rostering.shift', string='Rostered Shift', index='btree_not_null',
                                         ondelete='set null', readonly=True, copy=False)
    rostering_leave_id = fields.Many2one('rostering.leave', string='Leave Request', index='btree_not_null',
                                         ondelete='set null', readonly=True, copy=False)


class AdvancedTimesheet(models.Model):
    _inherit = 'advanced.timesheet'

    def _rostering_person_domain(self):
        """Shifts and leave of the timesheet's person: by employee when both
        apps know employees (Personnel), otherwise by user."""
        self.ensure_one()
        shift_fields = self.env['rostering.shift']._fields
        if 'employee_id' in self._fields and 'employee_id' in shift_fields and self.employee_id:
            return [('employee_id', '=', self.employee_id.id)]
        if self.user_id:
            return [('user_id', '=', self.user_id.id)]
        return []

    def action_fill_from_roster(self):
        self.ensure_one()
        self.check_access('write')
        if self.state != 'draft':
            raise UserError(_('Submitted timesheets cannot be changed. Reset it to draft first.'))
        person = self._rostering_person_domain()
        if not person:
            raise UserError(_('This timesheet has nobody to fill in the roster for.'))
        shifts = self.env['rostering.shift'].sudo().search(person + [
            ('roster_state', '=', 'published'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
        ], order='date, start_time, id')
        leaves = self.env['rostering.leave'].sudo().search(person + [
            ('state', '=', 'approved'),
            ('date_from', '<=', self.date_end),
            ('date_to', '>=', self.date_start),
        ])
        filled_shifts = self.line_ids.rostering_shift_id
        filled_leave_days = {(line.rostering_leave_id.id, line.date) for line in self.line_ids if line.rostering_leave_id}

        vals_list = []
        for shift in shifts - filled_shifts:
            hours = shift.paid_hours
            if shift.on_leave:
                if shift.leave_id.request_unit != 'partial':
                    continue  # the leave's entry covers the day
                hours = max(hours - shift.leave_id.hours, 0.0)  # worked the rest of the shift
                if not hours:
                    continue
            vals_list.append({
                'sheet_id': self.id,
                'date': shift.date,
                'work_type_id': shift.duty_id.work_type_id.id,
                'name': shift.duty_id.name or shift.standard_shift_id.name or _('Rostered shift'),
                'unit_amount': hours,
                'rostering_shift_id': shift.id,
            })
        for leave in leaves:
            # The leave's own hours per day: whole days at full-time hours, or the
            # part day's hours; public holidays are already left out.
            for day, hours in sorted(leave._hours_by_day().items()):
                if not self.date_start <= day <= self.date_end or (leave.id, day) in filled_leave_days:
                    continue
                if hours:
                    vals_list.append({
                        'sheet_id': self.id,
                        'date': day,
                        'work_type_id': leave.leave_type_id.work_type_id.id,
                        'name': leave.leave_type_id.name,
                        'unit_amount': hours,
                        'rostering_leave_id': leave.id,
                    })

        lines = self.env['advanced.timesheet.line'].create(vals_list)
        if lines:
            self.message_post(body=_('%s entries filled in from the roster and approved leave.', len(lines)))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if lines else 'info',
                'message': _('%s entries added from the roster and approved leave.', len(lines)) if lines
                else _('Nothing new to fill in: every published shift and approved leave day is already on this timesheet.'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

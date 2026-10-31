# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, fields, models


class PayrollSlipLine(models.Model):
    _inherit = 'payroll.slip.line'

    source = fields.Selection(selection_add=[('roster', 'Roster')], ondelete={'roster': 'set default'})


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_hours_vals_roster(self):
        """Published shifts (at their public holiday rate) and approved leave."""
        self.ensure_one()
        employee = self.employee_id
        ordinary = self.payroll_employee_id._ordinary_pay_item()
        hours = defaultdict(float)  # (pay item, holiday multiplier) -> hours

        shifts = self.env['rostering.shift'].sudo().search([
            ('employee_id', '=', employee.id),
            ('roster_state', '=', 'published'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
        ])
        for shift in shifts:
            worked = shift.paid_hours
            if shift.on_leave:
                if shift.leave_id.request_unit != 'partial':
                    continue  # the leave pays the day
                worked = max(worked - shift.leave_id.hours, 0.0)  # worked the rest of the shift
            multiplier = shift.holiday_pay_multiplier if shift.holiday_pay_multiplier > 1 else 1.0
            hours[(shift.duty_id.payroll_pay_item_id or ordinary, multiplier)] += worked

        leave_item = self.env.ref('advanced_payroll.pay_item_leave')
        leaves = self.env['rostering.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'approved'),
            ('date_from', '<=', self.date_end),
            ('date_to', '>=', self.date_start),
        ])
        for leave in leaves.filtered(lambda l: not l.leave_type_id.payroll_unpaid):
            # The leave's own hours per day; public holidays are already left out.
            for day, day_hours in leave._hours_by_day().items():
                if self.date_start <= day <= self.date_end:
                    hours[(leave.leave_type_id.payroll_pay_item_id or leave_item, 1.0)] += day_hours

        vals = []
        for (item, multiplier), total in sorted(hours.items(), key=lambda p: (p[0][0].sequence, p[0][0].id, p[0][1])):
            if total <= 0:
                continue
            name = item.name if multiplier == 1.0 else _('%(item)s (Public Holiday ×%(rate)s)',
                                                        item=item.name, rate=f'{multiplier:g}')
            vals.append(self._payroll_hours_line_vals(item, total, source='roster', name=name,
                                                      multiplier=multiplier))
        return vals

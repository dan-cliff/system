# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, fields, models


class PayrollSlipLine(models.Model):
    _inherit = 'payroll.slip.line'

    source = fields.Selection(selection_add=[('attendance', 'Attendances')],
                              ondelete={'attendance': 'set default'})


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_hours_vals_attendance(self):
        """Ordinary hours from the attendances, and approved extra hours at
        their pay rate."""
        self.ensure_one()
        employee = self.employee_id
        tz_self = self.with_context(tz=employee.tz or self.env.user.tz or 'UTC')
        attendances = self.env['advanced.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '!=', False),
            ('check_in', '>=', datetime.combine(self.date_start - timedelta(days=1), time.min)),
            ('check_in', '<=', datetime.combine(self.date_end + timedelta(days=1), time.max)),
        ]).filtered(lambda a: self.date_start
                    <= fields.Datetime.context_timestamp(tz_self, a.check_in).date()
                    <= self.date_end)
        # Missing hours (negative extra hours) are already left out of the worked hours.
        ordinary = sum(attendances.mapped('worked_hours')) - sum(max(a.overtime_hours, 0.0) for a in attendances)

        extra = defaultdict(float)
        for line in self.env['advanced.attendance.overtime.line'].sudo().search([
            ('employee_id', '=', employee.id),
            ('status', '=', 'approved'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
        ]):
            extra[line.amount_rate or 1.0] += line.manual_duration

        profile = self.payroll_employee_id
        vals = []
        if ordinary > 0:
            vals.append(self._payroll_hours_line_vals(profile._ordinary_pay_item(), ordinary, source='attendance'))
        overtime_item = self.env.ref('advanced_payroll.pay_item_overtime_15')
        for rate, hours in sorted(extra.items()):
            if hours > 0:
                # Paid at the extra hours' own rate, not the item's multiplier.
                vals.append(self._payroll_hours_line_vals(
                    overtime_item, hours, source='attendance',
                    name=_('Extra Hours ×%s', f'{rate:g}'),
                    multiplier=rate / (overtime_item.rate_multiplier or 1.0),
                ))
        return vals

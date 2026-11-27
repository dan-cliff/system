# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdvancedTimesheetWorkType(models.Model):
    _inherit = 'advanced.timesheet.work.type'

    payroll_pay_item_id = fields.Many2one(
        'payroll.pay.item', string='Pay Item', domain="[('calculation', '=', 'hours')]",
        help='How Payroll pays the hours of this work type. Leave empty for Ordinary Hours.',
    )


class AdvancedTimesheet(models.Model):
    _inherit = 'advanced.timesheet'

    @api.model
    def _payroll_ready_states(self):
        """States of timesheets Payroll pays: approved ones, or submitted
        ones when timesheets need no approval."""
        return ('approved',) if self._approval_required() else ('submitted', 'approved')

    def action_submit(self):
        result = super().action_submit()
        if not self._approval_required():
            self._payroll_refresh_slips()
        return result

    def action_approve(self):
        result = super().action_approve()
        self._payroll_refresh_slips()
        return result

    def _payroll_refresh_slips(self):
        """Recompute the employees' draft payslips that cover these timesheets."""
        Slip = self.env['payroll.slip'].sudo()
        if Slip._payroll_hours_source() != 'timesheet':
            return
        slips = Slip.browse()
        for sheet in self.sudo().filtered('employee_id'):
            slips |= Slip.search([
                ('employee_id', '=', sheet.employee_id.id),
                ('state', '=', 'draft'),
                ('date_start', '<=', sheet.date_end),
                ('date_end', '>=', sheet.date_start),
            ])
        slips._payroll_compute()

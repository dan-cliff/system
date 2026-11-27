# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models


class PayrollSlipLine(models.Model):
    _inherit = 'payroll.slip.line'

    source = fields.Selection(selection_add=[('timesheet', 'Timesheet')], ondelete={'timesheet': 'set default'})


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    timesheet_ids = fields.Many2many('advanced.timesheet', string='Timesheets', readonly=True, copy=False,
                                     help='The approved timesheets this payslip was filled from.')
    timesheet_count = fields.Integer(compute='_compute_timesheet_info')
    timesheet_pending_count = fields.Integer(
        string='Timesheets Waiting', compute='_compute_timesheet_info',
        help='Timesheets of this pay period that are not approved yet, so they are not paid.',
    )
    payroll_from_timesheets = fields.Boolean(compute='_compute_timesheet_info')

    @api.depends('timesheet_ids', 'employee_id', 'date_start', 'date_end', 'state')
    def _compute_timesheet_info(self):
        Sheet = self.env['advanced.timesheet'].sudo()
        source_is_timesheet = self._payroll_hours_source() == 'timesheet'
        ready = Sheet._payroll_ready_states()
        for slip in self:
            slip.timesheet_count = len(slip.timesheet_ids)
            slip.payroll_from_timesheets = (source_is_timesheet
                                            and slip.payroll_employee_id.pay_basis == 'hourly')
            if slip.payroll_from_timesheets and slip.state == 'draft' and slip.employee_id and slip.date_start:
                slip.timesheet_pending_count = Sheet.search_count(slip._payroll_timesheet_domain()
                                                                  + [('state', 'not in', ready)])
            else:
                slip.timesheet_pending_count = 0

    def _payroll_timesheet_domain(self):
        self.ensure_one()
        return [
            ('employee_id', '=', self.employee_id.id),
            ('date_start', '<=', self.date_end),
            ('date_end', '>=', self.date_start),
        ]

    def _payroll_compute(self):
        # Timesheets are listed again by each compute that fills from them.
        self.filtered(lambda s: s.state == 'draft').sudo().write({'timesheet_ids': [(5, 0, 0)]})
        return super()._payroll_compute()

    def _payroll_hours_vals_timesheet(self):
        """A line per Pay Item with the hours of the approved timesheets."""
        self.ensure_one()
        Sheet = self.env['advanced.timesheet'].sudo()
        sheets = Sheet.search(self._payroll_timesheet_domain()
                              + [('state', 'in', Sheet._payroll_ready_states())])
        lines = sheets.line_ids.filtered(lambda l: self.date_start <= l.date <= self.date_end)
        ordinary = self.payroll_employee_id._ordinary_pay_item()
        hours = defaultdict(float)
        for line in lines:
            hours[line.work_type_id.payroll_pay_item_id or ordinary] += line.unit_amount
        self.sudo().timesheet_ids = [(6, 0, lines.sheet_id.ids)]
        return [self._payroll_hours_line_vals(item, total, source='timesheet')
                for item, total in sorted(hours.items(), key=lambda pair: (pair[0].sequence, pair[0].id))
                if total]

    def action_open_timesheets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Timesheets'),
            'res_model': 'advanced.timesheet',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.timesheet_ids.ids)],
            'context': {'create': False},
        }

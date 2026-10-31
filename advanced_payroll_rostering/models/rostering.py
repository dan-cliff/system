# -*- coding: utf-8 -*-
from odoo import fields, models


class RosteringDuty(models.Model):
    _inherit = 'rostering.duty'

    payroll_pay_item_id = fields.Many2one(
        'payroll.pay.item', string='Pay Item', domain="[('calculation', '=', 'hours')]",
        help='How Payroll pays shifts of this duty. Leave empty for Ordinary Hours.',
    )


class RosteringLeaveType(models.Model):
    _inherit = 'rostering.leave.type'

    payroll_pay_item_id = fields.Many2one(
        'payroll.pay.item', string='Pay Item', domain="[('calculation', '=', 'hours')]",
        help='How Payroll pays this leave. Leave empty for Paid Leave.',
    )
    payroll_unpaid = fields.Boolean(string='Unpaid', help='Payroll does not pay this leave.')

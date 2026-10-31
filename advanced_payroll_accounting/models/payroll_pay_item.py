# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollPayItem(models.Model):
    _inherit = 'payroll.pay.item'

    account_id = fields.Many2one(
        'account.account', string='Account', company_dependent=True,
        help='Expense account for earnings, leave, allowances and reimbursements; liability account for '
             'deductions. Leave empty for the company\'s default (Settings › Payroll › Accounting).',
    )

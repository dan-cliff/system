# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollRule(models.Model):
    _inherit = 'payroll.rule'

    account_id = fields.Many2one(
        'account.account', string='Payable Account', company_dependent=True,
        help='Liability account the amounts are owed on (e.g. PAYG Withholding Payable, Superannuation '
             'Payable). Leave empty for the company\'s Payroll Liabilities account.',
    )
    expense_account_id = fields.Many2one(
        'account.account', string='Expense Account', company_dependent=True,
        help='For employer contributions: the expense account. Leave empty for the company\'s Wages '
             'Expense account.',
    )

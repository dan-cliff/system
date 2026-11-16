from odoo import fields, models


class AdvancedExpenseCategory(models.Model):
    _inherit = 'advanced.expense.category'

    account_id = fields.Many2one(
        'account.account', string='Expense Account', company_dependent=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', "
               "'liability_credit_card', 'off_balance'))]",
        help='Account the bills of this category are booked to. Empty: the expense account of the journal.')

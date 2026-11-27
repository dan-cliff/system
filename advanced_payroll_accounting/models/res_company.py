# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payroll_journal_id = fields.Many2one(
        'account.journal', string='Payroll Journal', domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Journal of the entries of approved pay runs.',
    )
    payroll_payment_journal_id = fields.Many2one(
        'account.journal', string='Payroll Payment Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', id)]",
        help='Bank or cash journal net wages are paid from. Leave empty to record payments in Accounting yourself.',
    )
    payroll_expense_account_id = fields.Many2one(
        'account.account', string='Wages Expense Account',
        help='Expense account of pay items and employer contributions that have none of their own.',
    )
    payroll_liability_account_id = fields.Many2one(
        'account.account', string='Payroll Liabilities Account',
        help='Liability account of tax, deductions and contributions that have none of their own.',
    )
    payroll_net_account_id = fields.Many2one(
        'account.account', string='Net Wages Payable Account',
        help='Liability account of the net wages owed to employees until they are paid.',
    )

    def _payroll_ensure_journal(self):
        """The company's Payroll journal, made if it has a chart of accounts but no journal yet."""
        self.ensure_one()
        if self.payroll_journal_id:
            return self.payroll_journal_id
        Journal = self.env['account.journal'].sudo()
        if not Journal.search_count([('company_id', '=', self.id)], limit=1):
            return Journal  # no chart of accounts yet
        journal = Journal.search([('company_id', '=', self.id), ('code', '=', 'PAYR')], limit=1) or Journal.create({
            'name': _('Payroll'),
            'code': 'PAYR',
            'type': 'general',
            'company_id': self.id,
        })
        self.sudo().payroll_journal_id = journal
        return journal

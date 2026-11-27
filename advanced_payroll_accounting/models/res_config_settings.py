# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payroll_journal_id = fields.Many2one(related='company_id.payroll_journal_id', readonly=False)
    payroll_payment_journal_id = fields.Many2one(related='company_id.payroll_payment_journal_id', readonly=False)
    payroll_expense_account_id = fields.Many2one(related='company_id.payroll_expense_account_id', readonly=False)
    payroll_liability_account_id = fields.Many2one(related='company_id.payroll_liability_account_id',
                                                   readonly=False)
    payroll_net_account_id = fields.Many2one(related='company_id.payroll_net_account_id', readonly=False)

    def action_payroll_create_journal(self):
        self.ensure_one()
        self.company_id._payroll_ensure_journal()

# -*- coding: utf-8 -*-
import json
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.addons.advanced_payroll.models.payroll_pay_item import GROSS_CATEGORIES


class PayrollRun(models.Model):
    _inherit = 'payroll.run'

    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    payment_move_id = fields.Many2one('account.move', string='Payment Entry', readonly=True, copy=False)
    account_move_ids = fields.One2many('account.move', 'payroll_run_id', string='Journal Entries')
    account_move_count = fields.Integer(compute='_compute_account_move_count')

    def _compute_account_move_count(self):
        counts = dict(self.env['account.move'].sudo()._read_group(
            [('payroll_run_id', 'in', self.ids)], ['payroll_run_id'], ['__count']))
        for run in self:
            run.account_move_count = counts.get(run, 0)

    # ------------------------------------------------------------------
    # Accrual: the pay run's journal entry, posted on approval
    # ------------------------------------------------------------------
    def _payroll_after_approve(self):
        super()._payroll_after_approve()
        for run in self.sudo():
            run.move_id = run._payroll_create_move()

    def _payroll_accounts(self):
        """The company's default accounts and journal, or a friendly error."""
        self.ensure_one()
        company = self.company_id
        missing = [label for label, value in (
            (_('Payroll Journal'), company.payroll_journal_id or company._payroll_ensure_journal()),
            (_('Wages Expense Account'), company.payroll_expense_account_id),
            (_('Payroll Liabilities Account'), company.payroll_liability_account_id),
            (_('Net Wages Payable Account'), company.payroll_net_account_id),
        ) if not value]
        if missing:
            raise UserError(_(
                '%(run)s cannot be posted to Accounting yet: set the %(missing)s of %(company)s in '
                'Settings › Payroll › Accounting.',
                run=self.name, missing=', '.join(missing), company=company.name))
        return company

    def _payroll_move_line_key(self, account, amount, name, partner=None, analytic=None):
        return (account.id, partner.id if partner else False,
                json.dumps(analytic or {}, sort_keys=True), 'debit' if amount >= 0 else 'credit')

    def _payroll_create_move(self):
        self.ensure_one()
        company = self._payroll_accounts()
        run = self.with_company(company)
        totals = defaultdict(float)
        names = {}

        def add(account, amount, name, partner=None, analytic=None):
            if run.currency_id.is_zero(amount):
                return
            key = run._payroll_move_line_key(account, amount, name, partner, analytic)
            totals[key] += amount
            names.setdefault(key, name)

        for slip in run.slip_ids.with_company(company):
            profile = slip.payroll_employee_id
            analytic = profile.analytic_distribution or None
            partner = slip.employee_id.work_contact_id
            for line in slip.line_ids:
                source = line.rule_id or line.pay_item_id
                if line.category in GROSS_CATEGORIES + ('reimbursement',):
                    add(source.account_id or company.payroll_expense_account_id, line.amount, line.name,
                        analytic=analytic)
                elif line.category in ('tax', 'deduction'):
                    add(source.account_id or company.payroll_liability_account_id, -line.amount, line.name)
                elif line.category == 'employer':
                    expense = (line.rule_id.expense_account_id if line.rule_id else False) \
                        or company.payroll_expense_account_id
                    add(expense, line.amount, line.name, analytic=analytic)
                    add(source.account_id or company.payroll_liability_account_id, -line.amount, line.name)
            add(company.payroll_net_account_id, -slip.net_amount, _('Net wages: %s', slip.employee_id.name),
                partner=partner)

        line_vals = []
        for (account_id, partner_id, analytic, _side), amount in totals.items():
            line_vals.append({
                'account_id': account_id,
                'partner_id': partner_id,
                'name': names[(account_id, partner_id, analytic, _side)],
                'debit': amount if amount > 0 else 0.0,
                'credit': -amount if amount < 0 else 0.0,
                'analytic_distribution': json.loads(analytic) or False,
            })
        move = self.env['account.move'].sudo().with_company(company).create({
            'move_type': 'entry',
            'journal_id': company.payroll_journal_id.id,
            'date': run.date_end,
            'ref': run.name,
            'payroll_run_id': run.id,
            'line_ids': [(0, 0, vals) for vals in line_vals],
        })
        move.action_post()
        run.message_post(body=_('Journal entry %s posted.', move._get_html_link()))
        return move

    # ------------------------------------------------------------------
    # Payment: posted when the pay run is marked as paid
    # ------------------------------------------------------------------
    def _payroll_after_paid(self):
        super()._payroll_after_paid()
        for run in self.sudo():
            if run.company_id.payroll_payment_journal_id:
                run.payment_move_id = run._payroll_create_payment_move()

    def _payroll_create_payment_move(self):
        self.ensure_one()
        company = self._payroll_accounts()
        journal = company.payroll_payment_journal_id
        bank_account = journal.default_account_id
        if not bank_account:
            raise UserError(_('The payment journal %s has no default account.', journal.name))
        line_vals = []
        for slip in self.slip_ids.filtered(lambda s: not self.currency_id.is_zero(s.net_amount)):
            line_vals.append({
                'account_id': company.payroll_net_account_id.id,
                'partner_id': slip.employee_id.work_contact_id.id,
                'name': _('Net wages: %s', slip.employee_id.name),
                'debit': slip.net_amount,
                'credit': 0.0,
            })
        total = sum(self.slip_ids.mapped('net_amount'))
        line_vals.append({'account_id': bank_account.id, 'name': self.name, 'debit': 0.0, 'credit': total})
        move = self.env['account.move'].sudo().with_company(company).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.payment_date,
            'ref': _('Payment: %s', self.name),
            'payroll_run_id': self.id,
            'line_ids': [(0, 0, vals) for vals in line_vals],
        })
        move.action_post()
        self._payroll_reconcile_net(move)
        self.message_post(body=_('Payment entry %s posted.', move._get_html_link()))
        return move

    def _payroll_reconcile_net(self, payment_move):
        """Match the net wages owed with their payment, employee by employee."""
        self.ensure_one()
        account = self.company_id.payroll_net_account_id
        if not account.reconcile or not self.move_id:
            return
        lines = (self.move_id | payment_move).line_ids.filtered(lambda l: l.account_id == account)
        for partner in lines.partner_id:
            lines.filtered(lambda l: l.partner_id == partner).reconcile()

    # ------------------------------------------------------------------
    # Reset to draft: reverse the entries
    # ------------------------------------------------------------------
    def _payroll_before_reset(self):
        super()._payroll_before_reset()
        today = fields.Date.context_today(self)
        for run in self.sudo():
            moves = (run.move_id | run.payment_move_id).filtered(lambda m: m.state == 'posted')
            if moves:
                moves.line_ids.filtered('reconciled').remove_move_reconcile()
                moves._reverse_moves(
                    default_values_list=[{'date': today, 'ref': _('Reversal of: %s', move.ref),
                                          'payroll_run_id': run.id} for move in moves],
                    cancel=True,
                )
                run.message_post(body=_('Journal entries reversed.'))
            run.write({'move_id': False, 'payment_move_id': False})

    def action_open_account_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('payroll_run_id', '=', self.id)],
            'context': {'create': False},
        }

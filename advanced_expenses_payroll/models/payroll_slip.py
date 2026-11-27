from odoo import _, fields, models


class PayrollSlipLine(models.Model):
    _inherit = 'payroll.slip.line'

    source = fields.Selection(selection_add=[('expense', 'Expense')], ondelete={'expense': 'set default'})
    expense_id = fields.Many2one('advanced.expense', string='Expense', readonly=True, index='btree_not_null',
                                 ondelete='set null')


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    advanced_expense_ids = fields.One2many('advanced.expense', 'payslip_id', string='Expenses')
    advanced_expense_count = fields.Integer(compute='_compute_advanced_expense_count')

    def _compute_advanced_expense_count(self):
        for slip in self:
            slip.advanced_expense_count = len(slip.advanced_expense_ids)

    def _payroll_compute(self):
        result = super()._payroll_compute()
        Expense = self.env['advanced.expense'].sudo()
        item = self.env.ref('advanced_payroll.pay_item_reimbursement', raise_if_not_found=False)
        Line = self.env['payroll.slip.line'].sudo()
        for slip in self.filtered(lambda s: s.state == 'draft'):
            slip.advanced_expense_ids.sudo().write({'payslip_id': False})
            if not slip.employee_id:
                continue
            expenses = Expense.search(Expense._payroll_reimbursable_domain(slip), order='date, id')
            for expense in expenses:
                Line.create({
                    'slip_id': slip.id,
                    'name': _('Expense %(ref)s: %(name)s', ref=expense.reference, name=expense.name),
                    'pay_item_id': item.id if item else False,
                    'category': 'reimbursement',
                    'source': 'expense',
                    'quantity': 1.0,
                    'rate': expense.total_amount_company,
                    'amount': expense.total_amount_company,
                    'expense_id': expense.id,
                })
            expenses.write({'payslip_id': slip.id})
        return result

    def write(self, vals):
        result = super().write(vals)
        state = vals.get('state')
        if state:
            expenses = self.sudo().advanced_expense_ids
            if state == 'paid':
                for slip in self:
                    slip.sudo().advanced_expense_ids.filtered(lambda e: e.state == 'approved')._do_mark_paid(
                        paid_date=slip.payment_date)
            elif state == 'cancelled':
                expenses.write({'payslip_id': False})
            elif state in ('draft', 'approved'):
                # A paid pay run was reset: the expenses are no longer reimbursed.
                expenses.filtered(lambda e: e.state == 'paid').write({'state': 'approved', 'paid_date': False})
        return result

    def action_open_advanced_expenses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expenses'),
            'res_model': 'advanced.expense',
            'view_mode': 'list,form',
            'domain': [('payslip_id', '=', self.id)],
        }

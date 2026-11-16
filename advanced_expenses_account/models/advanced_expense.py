from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

PAID_PAYMENT_STATES = ('paid', 'in_payment', 'reversed')


class AdvancedExpense(models.Model):
    _inherit = 'advanced.expense'

    state = fields.Selection(
        selection_add=[('posted', 'Posted'), ('paid',)],
        ondelete={'posted': lambda records: records.write({'state': 'approved'})},
        compute='_compute_state_from_move', store=True, readonly=False, precompute=True,
    )
    paid_date = fields.Date(compute='_compute_state_from_move', store=True, readonly=False, precompute=True)
    account_id = fields.Many2one(
        'account.account', string='Account', compute='_compute_account_id', store=True, readonly=False,
        precompute=True, check_company=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', "
               "'liability_credit_card', 'off_balance'))]",
        help='Account the bill of this expense is booked to.')
    account_move_id = fields.Many2one('account.move', string='Bill', readonly=True, copy=False,
                                      index='btree_not_null', ondelete='set null')
    payment_state = fields.Selection(related='account_move_id.payment_state', string='Payment Status')

    @api.depends('account_move_id.state', 'account_move_id.payment_state')
    def _compute_state_from_move(self):
        for expense in self:
            move = expense.account_move_id
            state = expense.state or 'draft'
            if move:
                if move.state == 'cancel':
                    state = 'approved'
                elif move.payment_state in PAID_PAYMENT_STATES:
                    state = 'paid'
                else:
                    state = 'posted'
            elif state == 'posted':
                # The bill was deleted.
                state = 'approved'
            if state == 'paid' and not expense.paid_date:
                expense.paid_date = fields.Date.context_today(expense)
            elif state != 'paid' and move:
                expense.paid_date = False
            else:
                expense.paid_date = expense.paid_date
            expense.state = state

    @api.depends('category_id', 'company_id')
    def _compute_account_id(self):
        for expense in self:
            account = expense.category_id.with_company(expense.company_id).account_id
            if account or not expense.account_id:
                expense.account_id = account

    @api.depends_context('uid')
    @api.depends('state', 'employee_id', 'approver_user_id', 'account_move_id')
    def _compute_permissions(self):
        super()._compute_permissions()
        can_pay = self.env.user.has_group('advanced_expenses.group_expense_pay')
        for expense in self:
            expense.can_pay = can_pay and expense.state == 'approved' and not expense.account_move_id

    def write(self, vals):
        if 'account_id' in vals and not self.env.su:
            posted = self.filtered('account_move_id')
            if posted:
                raise UserError(_('%s already has a bill: change the account on the bill.',
                                  ', '.join(posted.mapped('display_name'))))
        return super().write(vals)

    def _on_reset(self):
        billed = self.filtered(lambda e: e.account_move_id and e.account_move_id.state != 'cancel')
        if billed:
            raise UserError(_('%s already has a bill. Cancel the bill first.',
                              ', '.join(billed.mapped('display_name'))))
        self.filtered('account_move_id').write({'account_move_id': False})
        return super()._on_reset()

    # ------------------------------------------------------------------
    # Bills
    # ------------------------------------------------------------------
    def action_create_bill(self):
        self._check_can_pay()
        for expense in self:
            if expense.state != 'approved' or expense.account_move_id:
                raise UserError(_('%s is not an approved expense without a bill.', expense.display_name))
        moves = self.sudo()._create_bills()
        if len(moves) == 1 and self.env.user.has_group('account.group_account_invoice'):
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': moves.id,
            }
        return True

    def action_mark_paid(self):
        billed = self.filtered('account_move_id')
        if billed:
            raise UserError(_('%s has a bill: register the payment on the bill.',
                              ', '.join(billed.mapped('display_name'))))
        return super().action_mark_paid()

    def _bill_partner(self):
        self.ensure_one()
        if self.paid_by == 'company':
            if not self.vendor_id:
                raise UserError(_('Choose the Vendor of %s: its bill goes to the vendor.', self.display_name))
            return self.vendor_id
        partner = self.employee_id.sudo().work_contact_id
        if not partner:
            raise UserError(_('%s has no work contact to bill the expense to.', self.employee_id.name))
        return partner

    def _bill_journal(self):
        self.ensure_one()
        journal = self.company_id.expense_journal_id
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_('%s has no purchase journal for expense bills.', self.company_id.name))
        return journal

    def _bill_vals(self):
        self.ensure_one()
        journal = self._bill_journal()
        account = self.account_id or journal.default_account_id
        if not account:
            raise UserError(_('Choose the Account of %s, or an Expense Account on its category.', self.display_name))
        line_name = '%s: %s' % (self.employee_id.name, self.name)
        return {
            'move_type': 'in_invoice',
            'partner_id': self._bill_partner().id,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': self.date,
            'date': self.date,
            'ref': '%s %s' % (self.reference, self.name),
            'invoice_line_ids': [Command.create({
                'name': line_name,
                'account_id': account.id,
                'quantity': 1,
                'price_unit': self.total_amount,
                'tax_ids': [Command.clear()],
            })],
        }

    def _create_bills(self):
        moves = self.env['account.move']
        for expense in self:
            move = self.env['account.move'].with_company(expense.company_id).create(expense._bill_vals())
            move.action_post()
            move.message_post(body=_('Bill for the expense %s.', expense._get_html_link()))
            expense.account_move_id = move
            expense.message_post(body=_('Bill %s created.', move._get_html_link()))
            moves |= move
        return moves

    def action_open_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.account_move_id.id,
        }

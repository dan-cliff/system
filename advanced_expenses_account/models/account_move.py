from odoo import _, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    advanced_expense_ids = fields.One2many('advanced.expense', 'account_move_id', string='Expenses')
    advanced_expense_count = fields.Integer(compute='_compute_advanced_expense_count')

    def _compute_advanced_expense_count(self):
        for move in self:
            move.advanced_expense_count = len(move.advanced_expense_ids)

    def action_open_advanced_expenses(self):
        self.ensure_one()
        expenses = self.advanced_expense_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Expenses'),
            'res_model': 'advanced.expense',
            'view_mode': 'list,form',
            'domain': [('id', 'in', expenses.ids)],
        }
        if len(expenses) == 1:
            action.update(view_mode='form', res_id=expenses.id)
        return action

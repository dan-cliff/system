from odoo import fields, models


class AdvancedExpenseRefuseWizard(models.TransientModel):
    _name = 'advanced.expense.refuse.wizard'
    _description = 'Refuse Expenses'

    expense_ids = fields.Many2many('advanced.expense', string='Expenses', required=True)
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.expense_ids._do_refuse(self.reason)
        return {'type': 'ir.actions.act_window_close'}

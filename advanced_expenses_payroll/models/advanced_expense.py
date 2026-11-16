from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvancedExpense(models.Model):
    _inherit = 'advanced.expense'

    payslip_id = fields.Many2one('payroll.slip', string='Payslip', readonly=True, copy=False,
                                 index='btree_not_null', ondelete='set null',
                                 help='The payslip that reimburses this expense.')

    def _payroll_reimbursable_domain(self, slip):
        domain = [
            ('employee_id', '=', slip.employee_id.id),
            ('company_id', '=', slip.company_id.id),
            ('state', '=', 'approved'),
            ('paid_by', '=', 'employee'),
            ('date', '<=', slip.date_end),
            '|', ('payslip_id', '=', False), ('payslip_id', '=', slip.id),
        ]
        if 'account_move_id' in self._fields:
            domain.append(('account_move_id', '=', False))
        return domain

    def _on_approved(self):
        result = super()._on_approved()
        employees = self.filtered(lambda e: e.paid_by == 'employee').employee_id
        if employees:
            slips = self.env['payroll.slip'].sudo().search([
                ('employee_id', 'in', employees.ids), ('state', '=', 'draft')])
            slips._payroll_compute()
        return result

    def _on_reset(self):
        for expense in self.filtered('payslip_id'):
            if expense.payslip_id.state != 'draft':
                raise UserError(_('%(expense)s is reimbursed on the payslip %(slip)s, which is no longer a draft.',
                                  expense=expense.display_name, slip=expense.payslip_id.name))
        slips = self.payslip_id
        self.sudo().write({'payslip_id': False})
        slips.sudo()._payroll_compute()
        return super()._on_reset()

    def action_create_bill(self):
        on_slip = self.filtered('payslip_id')
        if on_slip:
            raise UserError(_('%s is reimbursed through payroll.', ', '.join(on_slip.mapped('display_name'))))
        return super().action_create_bill()

    def action_mark_paid(self):
        on_slip = self.filtered('payslip_id')
        if on_slip:
            raise UserError(_('%s is reimbursed through payroll: it is paid with its pay run.',
                              ', '.join(on_slip.mapped('display_name'))))
        return super().action_mark_paid()

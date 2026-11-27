from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    expense_approver_id = fields.Many2one(
        'res.users', string='Expenses Approver', groups='hr.group_hr_user', tracking=True,
        domain="[('share', '=', False)]",
        help="Approves this employee's expenses. Leave empty for their manager.")
    advanced_expense_ids = fields.One2many('advanced.expense', 'employee_id', string='Expenses')
    advanced_expense_count = fields.Integer(compute='_compute_advanced_expense_count', groups='hr.group_hr_user')

    def _compute_advanced_expense_count(self):
        counts = dict(self.env['advanced.expense']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count']))
        for employee in self:
            employee.advanced_expense_count = counts.get(employee, 0)

    def action_open_advanced_expenses(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_expenses.action_expense_all')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

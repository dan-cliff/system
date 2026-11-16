from odoo import _, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    advanced_expense_ids = fields.One2many('advanced.expense', 'project_id', string='Expenses')
    advanced_expense_count = fields.Integer(compute='_compute_advanced_expenses')
    advanced_expense_total = fields.Monetary(string='Expenses Cost', compute='_compute_advanced_expenses',
                                             currency_field='currency_id',
                                             help='Approved and paid expenses booked to the project.')

    def _compute_advanced_expenses(self):
        Expense = self.env['advanced.expense'].sudo()
        counts = dict(Expense._read_group([('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        totals = dict(Expense._read_group(
            [('project_id', 'in', self.ids), ('state', 'not in', ('draft', 'submitted', 'refused'))],
            ['project_id'], ['total_amount_company:sum']))
        for project in self:
            project.advanced_expense_count = counts.get(project, 0)
            project.advanced_expense_total = totals.get(project, 0.0)

    def action_open_advanced_expenses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expenses'),
            'res_model': 'advanced.expense',
            'view_mode': 'list,form,pivot,graph',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

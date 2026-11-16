from odoo import fields, models


class AdvancedExpenseCategory(models.Model):
    _name = 'advanced.expense.category'
    _description = 'Expense Category'
    _order = 'sequence, name, id'

    name = fields.Char(string='Category', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Leave empty to offer the category in every company.')
    cost = fields.Float(
        string='Unit Cost', digits='Product Price',
        help='A fixed cost per unit (e.g. per km for mileage): expenses then enter a quantity and the '
             'total is worked out. Leave at 0 to enter the total from the receipt.')
    unit_name = fields.Char(string='Unit', translate=True, help='What the quantity counts, e.g. km or nights.')
    receipt_required = fields.Boolean(
        string='Receipt Required', default=True,
        help='Expenses in this category can only be submitted with a receipt attached.')
    description = fields.Text(string='Guidelines', translate=True,
                              help='Shown on expenses in this category, e.g. what can be claimed.')
    expense_count = fields.Integer(compute='_compute_expense_count')
    # Odoo Expenses product this category was copied from (see hooks.py).
    legacy_product_id = fields.Integer(readonly=True, copy=False, index='btree_not_null')

    def _compute_expense_count(self):
        counts = dict(self.env['advanced.expense']._read_group(
            [('category_id', 'in', self.ids)], ['category_id'], ['__count']))
        for category in self:
            category.expense_count = counts.get(category, 0)

    def action_open_expenses(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_expenses.action_expense_all')
        action['domain'] = [('category_id', '=', self.id)]
        action['context'] = {'default_category_id': self.id}
        return action

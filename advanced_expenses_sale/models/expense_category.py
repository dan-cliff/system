from odoo import fields, models


class AdvancedExpenseCategory(models.Model):
    _inherit = 'advanced.expense.category'

    sale_product_id = fields.Many2one(
        'product.product', string='Re-invoice Product', check_company=True,
        domain="[('sale_ok', '=', True)]",
        help='Product of the sales order line when an expense of this category is re-invoiced. '
             'Empty: "Re-invoiced Expense".')

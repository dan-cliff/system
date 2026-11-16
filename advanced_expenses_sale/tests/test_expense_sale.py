from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestExpenseSale(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('advanced_expenses.group_expenses_admin')
        cls.employee = cls.env['hr.employee'].create({'name': 'Travelling Employee'})
        cls.category = cls.env['advanced.expense.category'].create({'name': 'Travel Test', 'receipt_required': False})
        customer = cls.env['res.partner'].create({'name': 'Customer'})
        service = cls.env['product.product'].create({'name': 'Consulting', 'type': 'service', 'list_price': 100})
        cls.order = cls.env['sale.order'].create({
            'partner_id': customer.id, 'order_line': [(0, 0, {'product_id': service.id})]})
        cls.order.action_confirm()

    def test_reinvoice(self):
        expense = self.env['advanced.expense'].create({
            'name': 'Train', 'employee_id': self.employee.id, 'category_id': self.category.id,
            'total_amount': 45.0, 'sale_order_id': self.order.id})
        expense.action_submit()
        expense.action_approve()
        line = expense.sale_order_line_id
        self.assertTrue(line)
        self.assertEqual(line.order_id, self.order)
        self.assertAlmostEqual(line.price_unit, 45.0)
        self.assertEqual(self.order.advanced_expense_count, 1)
        with self.assertRaises(UserError):
            expense.sale_order_id = False
        expense.action_reset_to_draft()
        self.assertFalse(expense.sale_order_line_id)
        # The confirmed order keeps the line, with nothing left to invoice.
        self.assertEqual(line.product_uom_qty, 0.0)
        self.assertFalse(line.advanced_expense_ids)

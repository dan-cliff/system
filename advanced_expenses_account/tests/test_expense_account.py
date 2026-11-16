from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestExpenseAccount(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('advanced_expenses.group_expenses_admin')
        cls.employee = cls.env['hr.employee'].sudo().create({'name': 'Billed Employee'})
        cls.category = cls.env['advanced.expense.category'].create({
            'name': 'Billed Category', 'receipt_required': False,
            'account_id': cls.company_data['default_account_expense'].id})

    def _approved_expense(self, **vals):
        values = {'name': 'Hotel', 'employee_id': self.employee.id, 'category_id': self.category.id,
                  'total_amount': 110.0}
        values.update(vals)
        expense = self.env['advanced.expense'].create(values)
        expense.action_submit()
        if expense.state == 'submitted':
            expense.action_approve()
        return expense

    def test_bill_and_payment(self):
        expense = self._approved_expense()
        self.assertEqual(expense.account_id, self.company_data['default_account_expense'])
        expense.action_create_bill()
        move = expense.account_move_id
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.partner_id, self.employee.work_contact_id)
        self.assertAlmostEqual(move.amount_total, 110.0)
        self.assertEqual(expense.state, 'posted')
        with self.assertRaises(UserError):
            expense.action_mark_paid()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create({})._create_payments()
        self.assertIn(move.payment_state, ('paid', 'in_payment'))
        self.assertEqual(expense.state, 'paid')
        self.assertTrue(expense.paid_date)

    def test_company_paid_needs_vendor(self):
        expense = self._approved_expense(paid_by='company')
        with self.assertRaises(UserError):
            expense.action_create_bill()
        expense.sudo().vendor_id = self.partner_a
        expense.action_create_bill()
        self.assertEqual(expense.account_move_id.partner_id, self.partner_a)

    def test_cancel_bill(self):
        expense = self._approved_expense()
        expense.action_create_bill()
        expense.account_move_id.button_draft()
        expense.account_move_id.button_cancel()
        self.assertEqual(expense.state, 'approved')
        expense.action_reset_to_draft()
        self.assertEqual(expense.state, 'draft')
        self.assertFalse(expense.account_move_id)

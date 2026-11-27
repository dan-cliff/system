import json
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdvancedExpenses(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        g = lambda key: cls.env.ref(f'advanced_expenses.group_{key}').id  # noqa: E731
        cls.manager_user = Users.create({
            'name': 'Expense Manager', 'login': 'exp_manager',
            'group_ids': [(6, 0, [g('expense_edit_team'), g('expense_approve')])],
        })
        cls.employee_user = Users.create({
            'name': 'Expense Employee', 'login': 'exp_employee',
            'group_ids': [(6, 0, [g('expense_edit_own'), g('expense_delete_own')])],
        })
        cls.other_user = Users.create({
            'name': 'Other Employee', 'login': 'exp_other',
            'group_ids': [(6, 0, [g('expense_edit_own')])],
        })
        cls.payer = Users.create({
            'name': 'Payer', 'login': 'exp_payer', 'group_ids': [(6, 0, [g('expense_pay')])],
        })
        Employee = cls.env['hr.employee']
        cls.manager = Employee.create({'name': 'Expense Manager', 'user_id': cls.manager_user.id})
        cls.employee = Employee.create({'name': 'Expense Employee', 'user_id': cls.employee_user.id,
                                        'parent_id': cls.manager.id})
        cls.other = Employee.create({'name': 'Other Employee', 'user_id': cls.other_user.id})
        cls.meals = cls.env.ref('advanced_expenses.expense_category_meals')
        cls.mileage = cls.env['advanced.expense.category'].create({
            'name': 'Test Mileage', 'cost': 0.5, 'unit_name': 'km', 'receipt_required': False})

    def _expense(self, user=None, **vals):
        env = self.env(user=user or self.employee_user)
        values = {'name': 'Lunch', 'category_id': self.mileage.id, 'quantity': 10}
        values.update(vals)
        return env['advanced.expense'].create(values)

    def test_fixed_cost_and_defaults(self):
        expense = self._expense()
        self.assertEqual(expense.employee_id, self.employee)
        self.assertEqual(expense.total_amount, 5.0)
        self.assertTrue(expense.reference.startswith('EXP/'))
        self.assertEqual(expense.approver_user_id, self.manager_user)

    def test_workflow(self):
        expense = self._expense()
        expense.action_submit()
        self.assertEqual(expense.state, 'submitted')
        self.assertTrue(expense.activity_ids)
        with self.assertRaises(UserError):
            expense.with_user(self.employee_user).write({'quantity': 20})
        # The employee can't approve their own expense.
        with self.assertRaises(UserError):
            expense.with_user(self.employee_user).action_approve()
        expense.with_user(self.manager_user).action_approve()
        self.assertEqual(expense.state, 'approved')
        self.assertFalse(expense.activity_ids)
        with self.assertRaises(UserError):
            expense.with_user(self.manager_user).action_mark_paid()
        expense.with_user(self.payer).action_mark_paid()
        self.assertEqual(expense.state, 'paid')

    def test_refuse_and_resubmit(self):
        expense = self._expense()
        expense.action_submit()
        wizard = self.env['advanced.expense.refuse.wizard'].with_user(self.manager_user).create({
            'expense_ids': [(6, 0, expense.ids)], 'reason': 'No receipt'})
        wizard.action_refuse()
        self.assertEqual(expense.state, 'refused')
        self.assertEqual(expense.refused_reason, 'No receipt')
        expense.with_user(self.employee_user).write({'quantity': 12})
        expense.with_user(self.employee_user).action_submit()
        self.assertEqual(expense.state, 'submitted')

    def test_receipt_required(self):
        expense = self._expense(category_id=self.meals.id, total_amount=20)
        with self.assertRaises(UserError):
            expense.action_submit()

    def test_access(self):
        expense = self._expense()
        # Someone else can't see it ...
        with self.assertRaises(AccessError):
            expense.with_user(self.other_user).read(['name'])
        # ... the manager sees and edits their team's.
        expense.with_user(self.manager_user).write({'name': 'Team lunch'})
        # Without a permission nothing is visible.
        nobody = self.env['res.users'].create({
            'name': 'Nobody', 'login': 'exp_nobody',
            'group_ids': [(6, 0, [self.env.ref('advanced_expenses.group_expenses_user').id])]})
        self.assertFalse(self.env['advanced.expense'].with_user(nobody).search([]))

    def test_no_manager_approval(self):
        self.env.company.expense_manager_approval = False
        expense = self._expense()
        expense.action_submit()
        self.assertEqual(expense.state, 'approved')

    def test_duplicates(self):
        first = self._expense()
        second = self._expense()
        self.assertEqual(second.duplicate_expense_ids, first)

    def test_ai_without_key(self):
        params = self.env['ir.config_parameter'].sudo()
        for key in ('claude_ai_settings.api_key', 'ai.anthropic_key', 'claude_ai_settings.gemini_api_key',
                    'ai.google_key'):
            params.set_param(key, False)
        expense = self._expense()
        self.assertFalse(expense.ai_available)
        with self.assertRaises(UserError):
            expense.action_ai_read_receipt()

    def test_form(self):
        with Form(self.env['advanced.expense'].with_user(self.employee_user)) as form:
            form.name = 'Taxi'
            form.category_id = self.mileage
            form.quantity = 4
        self.assertEqual(form.record.total_amount, 2.0)

    def test_report(self):
        expense = self._expense()
        content, _type = self.env['ir.actions.report']._render_qweb_html(
            'advanced_expenses.action_report_expense', expense.ids)
        self.assertIn(b'Expense Claim', content)

    def test_ai_read_receipt(self):
        self.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.api_key', 'test-key')
        expense = self._expense(category_id=self.meals.id, name='New expense', total_amount=1)
        with self.assertRaises(UserError):
            expense.get_ai_receipt_description()
        self.env['ir.attachment'].create({
            'name': 'receipt.png', 'raw': b'\x89PNG fake', 'mimetype': 'image/png',
            'res_model': 'advanced.expense', 'res_id': expense.id})
        vendor = self.env['res.partner'].create({'name': 'Corner Cafe'})
        answer = json.dumps({'description': 'Coffee with supplier', 'date': '2026-03-05', 'total': 12.5,
                             'tax': 1.14, 'currency': '', 'vendor': 'corner cafe', 'category': 'Meals'})
        with patch('odoo.addons.advanced_expenses.models.expense_ai.ai_read_file', return_value=answer) as call:
            info = expense.get_ai_receipt_description()
            self.assertEqual(info['provider'], 'Claude')
            self.assertEqual(info['receipt'], 'receipt.png')
            expense.action_ai_read_receipt()
        self.assertEqual(call.call_args.args[3], 'image/png')
        self.assertEqual(expense.name, 'Coffee with supplier')
        self.assertEqual(str(expense.date), '2026-03-05')
        self.assertEqual(expense.total_amount, 12.5)
        self.assertEqual(expense.tax_amount, 1.14)
        self.assertEqual(expense.vendor_id, vendor)
        self.assertEqual(expense.category_id, self.meals)

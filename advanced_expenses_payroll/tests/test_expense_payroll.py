from datetime import date
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestExpensePayroll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        PayrollRun = type(cls.env['payroll.run'])
        for hook in ('_payroll_after_approve', '_payroll_after_paid', '_payroll_before_reset'):
            cls.startClassPatcher(patch.object(PayrollRun, hook, lambda self: None))
        cls.env.user.group_ids |= cls.env.ref('advanced_expenses.group_expenses_admin')
        cls.weekly = cls.env.ref('advanced_payroll.pay_frequency_weekly')
        cls.country = cls.env['payroll.country'].create({
            'name': 'Expenseland', 'code': 'XL', 'country_id': cls.env.ref('base.be').id,
            'tax_year_start_month': 7, 'default_pay_frequency_id': cls.weekly.id,
            'standard_hours_per_week': 40,
            'ordinary_pay_item_id': cls.env.ref('advanced_payroll.pay_item_ordinary').id,
        })
        cls.employee = cls.env['hr.employee'].create({'name': 'Reimbursed Employee'})
        cls.env['payroll.employee'].create({
            'employee_id': cls.employee.id, 'country_id': cls.country.id, 'pay_frequency_id': cls.weekly.id,
            'pay_basis': 'salary', 'annual_salary': 52000,
        })
        cls.category = cls.env['advanced.expense.category'].create({'name': 'Payroll Test', 'receipt_required': False})

    def test_reimbursed_on_payslip(self):
        expense = self.env['advanced.expense'].create({
            'name': 'Parking', 'employee_id': self.employee.id, 'category_id': self.category.id,
            'total_amount': 30.0, 'date': date(2026, 7, 1)})
        company_paid = self.env['advanced.expense'].create({
            'name': 'Card', 'employee_id': self.employee.id, 'category_id': self.category.id,
            'total_amount': 50.0, 'date': date(2026, 7, 1), 'paid_by': 'company'})
        run = self.env['payroll.run'].create({
            'country_id': self.country.id, 'pay_frequency_id': self.weekly.id, 'date_start': date(2026, 7, 6)})
        run.action_generate_slips()
        slip = run.slip_ids.filtered(lambda s: s.employee_id == self.employee)
        (expense | company_paid).action_submit()
        (expense | company_paid).action_approve()
        # Approving refreshed the draft payslip.
        self.assertEqual(expense.payslip_id, slip)
        self.assertFalse(company_paid.payslip_id)
        line = slip.line_ids.filtered(lambda l: l.source == 'expense')
        self.assertEqual(line.category, 'reimbursement')
        self.assertAlmostEqual(line.amount, 30.0)
        self.assertAlmostEqual(slip.reimbursement_amount, 30.0)
        run.action_compute()
        self.assertEqual(expense.payslip_id, slip)
        run.action_approve()
        run.action_mark_paid()
        self.assertEqual(expense.state, 'paid')
        self.assertEqual(expense.paid_date, slip.payment_date)
        self.assertEqual(company_paid.state, 'approved')

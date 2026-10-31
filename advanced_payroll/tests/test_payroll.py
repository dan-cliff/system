# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPayroll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The core engine on its own: no journal entries (advanced_payroll_accounting)
        # and hourly employees on their standard hours.
        PayrollRun = type(cls.env['payroll.run'])
        for hook in ('_payroll_after_approve', '_payroll_after_paid', '_payroll_before_reset'):
            cls.startClassPatcher(patch.object(PayrollRun, hook, lambda self: None))
        cls.env['ir.config_parameter'].sudo().set_param('advanced_payroll.hours_source', 'standard')
        cls.weekly = cls.env.ref('advanced_payroll.pay_frequency_weekly')
        cls.fortnightly = cls.env.ref('advanced_payroll.pay_frequency_fortnightly')
        cls.country = cls.env['payroll.country'].create({
            'name': 'Testland',
            'code': 'TL',
            'country_id': cls.env.ref('base.be').id,
            'tax_year_start_month': 7,
            'default_pay_frequency_id': cls.weekly.id,
            'standard_hours_per_week': 40,
            'ordinary_pay_item_id': cls.env.ref('advanced_payroll.pay_item_ordinary').id,
        })
        cls.table = cls.env['payroll.tax.table'].create({
            'name': 'Test Brackets',
            'country_id': cls.country.id,
            'bracket_ids': [(0, 0, {'threshold': 0, 'rate': 0}),
                            (0, 0, {'threshold': 10000, 'rate': 10}),
                            (0, 0, {'threshold': 50000, 'rate': 20})],
        })
        cls.tax_rule = cls.env['payroll.rule'].create({
            'name': 'Income Tax', 'code': 'TL_TAX', 'country_id': cls.country.id, 'sequence': 10,
            'category': 'tax', 'compute_method': 'brackets', 'tax_table_id': cls.table.id,
        })
        cls.pension_rule = cls.env['payroll.rule'].create({
            'name': 'Pension', 'code': 'TL_PEN', 'country_id': cls.country.id, 'sequence': 20,
            'category': 'employer', 'compute_method': 'percentage', 'base': 'retirement', 'rate': 10,
            'annual_cap': 1500,
        })
        employee = cls.env['hr.employee'].create({'name': 'Pat Payee'})
        cls.profile = cls.env['payroll.employee'].create({
            'employee_id': employee.id,
            'country_id': cls.country.id,
            'pay_frequency_id': cls.weekly.id,
            'pay_basis': 'salary',
            'annual_salary': 52000,
        })

    def _run(self, day):
        run = self.env['payroll.run'].create({
            'country_id': self.country.id, 'pay_frequency_id': self.weekly.id, 'date_start': day,
        })
        run.action_generate_slips()
        return run

    def test_tax_table(self):
        self.assertAlmostEqual(self.table._annual_tax(5000), 0.0)
        self.assertAlmostEqual(self.table._annual_tax(30000), 2000.0)
        self.assertAlmostEqual(self.table._annual_tax(60000), 4000.0 + 2000.0)
        self.table.annual_deduction = 10000
        self.assertAlmostEqual(self.table._annual_tax(30000), 1000.0)
        self.table.write({'annual_deduction': 0, 'credit_base': 10000})
        self.assertAlmostEqual(self.table._annual_tax(30000), 1000.0, msg='Credited at the lowest rate (10%).')

    def test_periods(self):
        start, end = self.fortnightly._period_bounds(date(2026, 10, 31))
        self.assertEqual((end - start).days, 13)
        self.assertTrue(start <= date(2026, 10, 31) <= end)
        semi = self.env.ref('advanced_payroll.pay_frequency_semi_monthly')
        self.assertEqual(semi._period_bounds(date(2026, 2, 20)), (date(2026, 2, 16), date(2026, 2, 28)))
        monthly = self.env.ref('advanced_payroll.pay_frequency_monthly')
        self.assertEqual(monthly._period_bounds(date(2026, 12, 5)), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_salary_slip(self):
        run = self._run(date(2026, 8, 5))
        slip = run.slip_ids
        self.assertEqual(len(slip), 1)
        self.assertEqual((run.date_end - run.date_start).days, 6)
        self.assertAlmostEqual(slip.gross_amount, 1000.0)
        # 52,000 a year: (40,000 × 10% + 2,000 × 20%) / 52
        self.assertAlmostEqual(slip.tax_amount, round(4400 / 52, 2))
        self.assertAlmostEqual(slip.net_amount, 1000.0 - round(4400 / 52, 2))
        self.assertAlmostEqual(slip.employer_amount, 100.0)
        self.assertAlmostEqual(slip.hours, 40.0)

    def test_annual_cap_counts_year_to_date(self):
        amounts = []
        for day in (date(2026, 7, 8), date(2026, 7, 15)):
            run = self._run(day)
            amounts.append(run.slip_ids.employer_amount)
            run.action_approve()
        # Pension base is capped at 1,500 a tax year: 1,000 then 500.
        self.assertEqual(amounts, [100.0, 50.0])
        run = self._run(date(2026, 7, 22))
        self.assertFalse(run.slip_ids.line_ids.filtered(lambda l: l.rule_id == self.pension_rule))

    def test_entered_lines_are_kept(self):
        run = self._run(date(2026, 8, 5))
        slip = run.slip_ids
        self.env['payroll.slip.line'].create({
            'slip_id': slip.id,
            'pay_item_id': self.env.ref('advanced_payroll.pay_item_reimbursement').id,
            'name': 'Mileage',
            'amount': 80.0,
        })
        slip.action_compute()
        self.assertAlmostEqual(slip.reimbursement_amount, 80.0)
        self.assertAlmostEqual(slip.net_amount, 1000.0 - slip.tax_amount + 80.0)
        self.assertEqual(slip.taxable_amount, 1000.0, 'Reimbursements are not taxed.')

    def test_approved_run_is_locked(self):
        run = self._run(date(2026, 8, 5))
        run.action_approve()
        self.assertEqual(run.slip_ids.state, 'approved')
        with self.assertRaises(UserError):
            run.slip_ids.line_ids[0].amount = 1.0
        run.action_mark_paid()
        self.assertEqual(run.state, 'paid')
        run.action_reset_to_draft()
        self.assertEqual(run.slip_ids.state, 'draft')

    def test_hourly_standard_hours(self):
        self.profile.write({'pay_basis': 'hourly', 'hourly_rate': 30.0, 'hours_per_week': 20})
        slip = self._run(date(2026, 8, 5)).slip_ids
        self.assertAlmostEqual(slip.gross_amount, 600.0)

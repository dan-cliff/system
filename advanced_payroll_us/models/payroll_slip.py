# -*- coding: utf-8 -*-
from odoo import models


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_rule_applies(self, rule):
        if self.country_code == 'US' and rule.code == 'US_FIT':
            return not self.payroll_employee_id.us_exempt
        return super()._payroll_rule_applies(rule)

    def _payroll_tax_table(self, rule):
        if self.country_code == 'US' and rule.code == 'US_FIT':
            profile = self.payroll_employee_id
            status = profile.us_filing_status_id
            if profile.us_w4_step2 and status.step2_tax_table_id:
                return status.step2_tax_table_id
            return status.tax_table_id or rule.tax_table_id
        return super()._payroll_tax_table(rule)

    def _payroll_tax_adjustments(self, rule):
        adjust = super()._payroll_tax_adjustments(rule)
        if self.country_code == 'US' and rule.code == 'US_FIT':
            profile = self.payroll_employee_id
            adjust['annual_income'] += profile.us_w4_other_income
            adjust['annual_deduction'] += profile.us_w4_deductions
            adjust['annual_credit'] += profile.us_w4_dependents
            adjust['period_extra'] += profile.us_w4_extra_withholding
        return adjust

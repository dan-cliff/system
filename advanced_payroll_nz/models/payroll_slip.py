# -*- coding: utf-8 -*-
from odoo import models


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_rule_applies(self, rule):
        if self.country_code == 'NZ':
            profile = self.payroll_employee_id
            if rule.code == 'NZ_SL':
                return profile.nz_tax_code_id.student_loan
            if rule.code in ('NZ_KS_EE', 'NZ_KS_ER'):
                return profile.nz_kiwisaver_member
        return super()._payroll_rule_applies(rule)

    def _payroll_rule_rate(self, rule):
        if self.country_code == 'NZ':
            if rule.code == 'NZ_KS_EE':
                return self.payroll_employee_id.nz_kiwisaver_rate
            if rule.code == 'NZ_KS_ER':
                return self.payroll_employee_id.nz_kiwisaver_employer_rate
        return super()._payroll_rule_rate(rule)

    def _payroll_tax_table(self, rule):
        if self.country_code == 'NZ' and rule.code == 'NZ_PAYE':
            return self.payroll_employee_id.nz_tax_code_id.tax_table_id or rule.tax_table_id
        return super()._payroll_tax_table(rule)

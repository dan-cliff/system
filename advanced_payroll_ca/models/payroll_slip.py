# -*- coding: utf-8 -*-
from odoo import models


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_rule_applies(self, rule):
        if self.country_code == 'CA':
            profile = self.payroll_employee_id
            if rule.code in ('CA_CPP', 'CA_CPP2', 'CA_CPP_ER', 'CA_CPP2_ER'):
                return not profile.ca_cpp_exempt
            if rule.code in ('CA_EI', 'CA_EI_ER'):
                return not profile.ca_ei_exempt
            if rule.code == 'CA_PIT':
                return bool(profile.ca_province_id)
        return super()._payroll_rule_applies(rule)

    def _payroll_tax_table(self, rule):
        if self.country_code == 'CA' and rule.code == 'CA_PIT':
            return self.payroll_employee_id.ca_province_id.tax_table_id
        return super()._payroll_tax_table(rule)

    def _payroll_tax_adjustments(self, rule):
        adjust = super()._payroll_tax_adjustments(rule)
        if self.country_code == 'CA':
            profile = self.payroll_employee_id
            if rule.code == 'CA_FIT' and profile.ca_td1_federal:
                adjust['credit_base'] = profile.ca_td1_federal
            if rule.code == 'CA_PIT' and profile.ca_td1_provincial:
                adjust['credit_base'] = profile.ca_td1_provincial
        return adjust

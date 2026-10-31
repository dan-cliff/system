# -*- coding: utf-8 -*-
from odoo import models


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'

    def _payroll_rule_applies(self, rule):
        if self.country_code == 'AU' and rule.code == 'AU_MEDICARE':
            scale = self.payroll_employee_id.au_tax_scale_id
            return bool(scale.medicare_levy) if scale else True
        return super()._payroll_rule_applies(rule)

    def _payroll_tax_table(self, rule):
        if self.country_code == 'AU' and rule.code == 'AU_PAYG':
            return self.payroll_employee_id.au_tax_scale_id.tax_table_id or rule.tax_table_id
        return super()._payroll_tax_table(rule)

    def _payroll_tax_adjustments(self, rule):
        adjust = super()._payroll_tax_adjustments(rule)
        if self.country_code == 'AU' and rule.code == 'AU_PAYG':
            adjust['period_extra'] += self.payroll_employee_id.au_extra_withholding
        return adjust

# -*- coding: utf-8 -*-
from odoo import models


class PayrollSlip(models.Model):
    _inherit = 'payroll.slip'
    # With Personnel, payroll details are no longer opened from a menu: payslips
    # take their Organisation units from the employee (org_structure).
    _org_parent_field = 'employee_id'

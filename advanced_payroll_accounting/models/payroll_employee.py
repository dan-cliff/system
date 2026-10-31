# -*- coding: utf-8 -*-
from odoo import models


class PayrollEmployee(models.Model):
    # analytic_distribution: the employee's cost centres, carried by the expense lines.
    _name = 'payroll.employee'
    _inherit = ['payroll.employee', 'analytic.mixin']

# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollNzTaxCode(models.Model):
    """An Inland Revenue tax code, from the employee's IR330."""
    _name = 'payroll.nz.tax.code'
    _description = 'NZ Tax Code'
    _order = 'sequence, id'

    name = fields.Char(string='Tax Code', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    tax_table_id = fields.Many2one('payroll.tax.table', string='Tax Table', required=True,
                                   domain="[('country_id.code', '=', 'NZ')]")
    student_loan = fields.Boolean(string='Student Loan', help='Deduct student loan repayments.')
    description = fields.Text(string='Description')

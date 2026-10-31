# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollUsFilingStatus(models.Model):
    """A W-4 filing status and the tax table federal withholding uses for it."""
    _name = 'payroll.us.filing.status'
    _description = 'US Filing Status'
    _order = 'sequence, id'

    name = fields.Char(string='Filing Status', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    tax_table_id = fields.Many2one('payroll.tax.table', string='Tax Table', required=True,
                                   domain="[('country_id.code', '=', 'US')]",
                                   help='Brackets and standard deduction (the Annual Deduction) for this status.')
    step2_tax_table_id = fields.Many2one(
        'payroll.tax.table', string='Tax Table (Step 2 Checked)', domain="[('country_id.code', '=', 'US')]",
        help='Used when the W-4 Step 2 box (multiple jobs or spouse works) is checked.',
    )
    description = fields.Text(string='Description')

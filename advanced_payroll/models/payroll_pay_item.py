# -*- coding: utf-8 -*-
from odoo import api, fields, models

# What a pay item or rule line is. Totals, tax bases and the journal entry
# depend on these, so they stay a fixed selection (see CLAUDE.md > Choice
# fields); the items themselves are data.
CATEGORIES = [
    ('earning', 'Earning'),
    ('leave', 'Paid Leave'),
    ('allowance', 'Allowance'),
    ('reimbursement', 'Reimbursement'),
    ('deduction', 'Deduction'),
    ('tax', 'Tax'),
    ('employer', 'Employer Contribution'),
]
# Categories that make up gross pay.
GROSS_CATEGORIES = ('earning', 'leave', 'allowance')
# Categories taken off the employee's pay.
DEDUCTED_CATEGORIES = ('deduction', 'tax')


class PayrollPayItem(models.Model):
    _name = 'payroll.pay.item'
    _description = 'Pay Item'
    _order = 'sequence, name, id'

    name = fields.Char(string='Pay Item', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    country_id = fields.Many2one(
        'payroll.country', string='Payroll Country', index=True,
        help='Leave empty to offer the item in every country.',
    )
    category = fields.Selection(
        [c for c in CATEGORIES if c[0] not in ('tax', 'employer')],
        string='Category', required=True, default='earning',
        help='Earnings, paid leave and allowances make gross pay; reimbursements are added to net pay '
             'untaxed; deductions are taken off net pay. Tax and employer contributions come from '
             'Payroll Rules.',
    )
    calculation = fields.Selection(
        [('hours', 'Hours × Hourly Rate'), ('amount', 'Fixed Amount')],
        string='Calculation', required=True, default='hours',
        help='Hours are paid at the employee\'s hourly rate times the Rate Multiplier; fixed amounts are '
             'entered on each payslip.',
    )
    rate_multiplier = fields.Float(
        string='Rate Multiplier', digits=(16, 4), default=1.0,
        help='Times the hourly rate, e.g. 1.5 for time and a half, or 0.175 for leave loading.',
    )
    is_taxable = fields.Boolean(
        string='Taxable', compute='_compute_flags', store=True, readonly=False,
        help='Counted in the taxable pay the tax rules work from.',
    )
    retirement_eligible = fields.Boolean(
        string='Retirement Contributions', compute='_compute_flags', store=True, readonly=False,
        help='Counted in the pay retirement contributions are worked out from (e.g. Ordinary Time '
             'Earnings for superannuation, KiwiSaver gross earnings, pensionable earnings).',
    )
    description = fields.Text(string='Description')

    @api.depends('category')
    def _compute_flags(self):
        for item in self:
            item.is_taxable = item.category in GROSS_CATEGORIES
            item.retirement_eligible = item.category in ('earning', 'leave')

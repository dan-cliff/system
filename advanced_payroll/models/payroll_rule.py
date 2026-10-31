# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# How a rule is worked out: payroll.slip._payroll_compute_<method>(). Country
# apps add their own methods with selection_add, so this stays a technical
# selection (see CLAUDE.md > Choice fields).
COMPUTE_METHODS = [
    ('percentage', 'Percentage of Pay'),
    ('brackets', 'Tax Table'),
    ('fixed', 'Fixed Amount'),
]
# The pay a rule is worked out from (see payroll.slip._payroll_rule_base).
BASES = [
    ('taxable', 'Taxable Pay'),
    ('gross', 'Gross Pay'),
    ('retirement', 'Retirement Contribution Pay'),
]


class PayrollRule(models.Model):
    """A statutory (or company) rule run on every payslip of its country:
    income tax, social security, retirement contributions, levies, ..."""
    _name = 'payroll.rule'
    _description = 'Payroll Rule'
    _order = 'country_id, sequence, id'

    name = fields.Char(string='Payroll Rule', required=True, translate=True)
    code = fields.Char(
        string='Code', required=True,
        help='Technical code. Year-to-date amounts and the country apps\' own conditions follow it.',
    )
    sequence = fields.Integer(default=10, help='Rules run in this order.')
    active = fields.Boolean(default=True)
    country_id = fields.Many2one('payroll.country', string='Payroll Country', required=True, index=True)
    category = fields.Selection(
        [('tax', 'Tax'), ('deduction', 'Employee Contribution'), ('employer', 'Employer Contribution')],
        string='Category', required=True, default='tax',
        help='Tax and employee contributions are taken off the employee\'s pay; employer contributions are '
             'paid on top and count towards the employer cost.',
    )
    compute_method = fields.Selection(COMPUTE_METHODS, string='Worked Out As', required=True,
                                      default='percentage')
    base = fields.Selection(BASES, string='Based On', required=True, default='taxable')
    rate = fields.Float(string='Rate (%)', digits=(16, 4))
    fixed_amount = fields.Float(string='Amount per Pay Period')
    tax_table_id = fields.Many2one(
        'payroll.tax.table', string='Tax Table', domain="[('country_id', '=', country_id)]",
        help='Default tax table. Country apps can pick another one per employee (e.g. by tax code).',
    )
    annual_exemption = fields.Float(
        string='Annual Exemption',
        help='Taken off the pay of each period, spread evenly over the year\'s pay periods '
             '(e.g. a basic exemption). Thresholds and maximums count the pay after it.',
    )
    annual_threshold = fields.Float(
        string='Annual Threshold',
        help='The rule only applies to pay above this amount in the tax year, counted year to date.',
    )
    annual_cap = fields.Float(
        string='Annual Maximum',
        help='Pay above this amount in the tax year is left out, counted year to date (e.g. a wage base). '
             'Leave at 0 for no maximum.',
    )
    description = fields.Text(string='Description')

    _code_country_unique = models.Constraint('UNIQUE(code, country_id)',
                                             'Each rule of a country needs its own code.')

    @api.constrains('annual_threshold', 'annual_cap')
    def _check_cap(self):
        for rule in self:
            if rule.annual_cap and rule.annual_cap <= rule.annual_threshold:
                raise ValidationError(_('%s: the annual maximum must be above the annual threshold.', rule.name))

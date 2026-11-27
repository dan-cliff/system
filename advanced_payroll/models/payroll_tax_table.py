# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PayrollTaxTable(models.Model):
    """Progressive annual tax brackets. Payroll Rules worked out with "Tax
    Table" annualise the period's pay, apply the table and divide the tax
    back over the year's pay periods."""
    _name = 'payroll.tax.table'
    _description = 'Tax Table'
    _order = 'country_id, sequence, name, id'

    name = fields.Char(string='Tax Table', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    country_id = fields.Many2one('payroll.country', string='Payroll Country', required=True, index=True)
    bracket_ids = fields.One2many('payroll.tax.bracket', 'table_id', string='Brackets', copy=True)
    annual_deduction = fields.Float(
        string='Annual Deduction',
        help='Taken off the annual pay before the brackets apply, e.g. a standard deduction.',
    )
    credit_base = fields.Float(
        string='Annual Credit Base',
        help='A non-refundable credit (e.g. a basic personal amount) taken off the tax at the Credit Rate.',
    )
    credit_rate = fields.Float(
        string='Credit Rate (%)', digits=(16, 4),
        help='Rate the Annual Credit Base is credited at. Leave at 0 for the lowest bracket rate above 0%.',
    )
    note = fields.Text(string='Source and Notes')

    @api.constrains('bracket_ids')
    def _check_brackets(self):
        for table in self:
            thresholds = table.bracket_ids.mapped('threshold')
            if len(thresholds) != len(set(thresholds)):
                raise ValidationError(_('%s: two brackets start at the same amount.', table.name))

    def _lowest_rate(self):
        self.ensure_one()
        if self.credit_rate:
            return self.credit_rate
        rates = [b.rate for b in self.bracket_ids.sorted('threshold') if b.rate > 0]
        return rates[0] if rates else 0.0

    def _annual_tax(self, income, credit_base=None):
        """Tax on an annual ``income`` (before this table's deduction)."""
        self.ensure_one()
        income = max(income - self.annual_deduction, 0.0)
        brackets = self.bracket_ids.sorted('threshold')
        tax = 0.0
        for index, bracket in enumerate(brackets):
            upper = brackets[index + 1].threshold if index + 1 < len(brackets) else None
            if income <= bracket.threshold:
                break
            top = income if upper is None else min(income, upper)
            tax += (top - bracket.threshold) * bracket.rate / 100.0
        credit = self.credit_base if credit_base is None else credit_base
        tax -= credit * self._lowest_rate() / 100.0
        return max(tax, 0.0)


class PayrollTaxBracket(models.Model):
    _name = 'payroll.tax.bracket'
    _description = 'Tax Bracket'
    _order = 'table_id, threshold, id'

    table_id = fields.Many2one('payroll.tax.table', string='Tax Table', required=True, index=True,
                               ondelete='cascade')
    threshold = fields.Float(string='Annual Income Over', required=True, default=0.0,
                             help='The rate applies to annual income above this amount, up to the next bracket.')
    rate = fields.Float(string='Rate (%)', digits=(16, 4), required=True)

    @api.constrains('threshold', 'rate')
    def _check_values(self):
        if any(b.threshold < 0 or b.rate < 0 for b in self):
            raise ValidationError(_('Tax brackets cannot have negative amounts or rates.'))

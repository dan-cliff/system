# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PayrollCountry(models.Model):
    """A country payroll is run for. Each Payroll country app (e.g.
    advanced_payroll_au) ships one, with its pay items, tax tables and rules,
    and adds the country's own employee details."""
    _name = 'payroll.country'
    _description = 'Payroll Country'
    _order = 'sequence, name, id'

    name = fields.Char(string='Payroll Country', required=True, translate=True)
    code = fields.Char(
        string='Code', required=True,
        help='The country\'s ISO code (e.g. AU). The country apps use it to show their own details.',
    )
    country_id = fields.Many2one('res.country', string='Country', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    tax_year_start_month = fields.Integer(
        string='Tax Year Starts (Month)', required=True, default=1,
        help='Month the tax year starts in (1 = January, 7 = July). Year-to-date amounts and annual caps '
             'restart on that day.',
    )
    tax_year_start_day = fields.Integer(string='Tax Year Starts (Day)', required=True, default=1)
    default_pay_frequency_id = fields.Many2one('payroll.pay.frequency', string='Default Pay Frequency')
    standard_hours_per_week = fields.Float(string='Standard Hours a Week', default=38.0)
    ordinary_pay_item_id = fields.Many2one(
        'payroll.pay.item', string='Ordinary Pay Item',
        domain="[('category', '=', 'earning'), '|', ('country_id', '=', False), ('country_id', '=', id)]",
        help='Pay item of salaries and ordinary hours.',
    )
    pay_item_ids = fields.One2many('payroll.pay.item', 'country_id', string='Pay Items')
    rule_ids = fields.One2many('payroll.rule', 'country_id', string='Payroll Rules')
    tax_table_ids = fields.One2many('payroll.tax.table', 'country_id', string='Tax Tables')
    note = fields.Html(string='Notes')

    _code_unique = models.Constraint('UNIQUE(code)', 'Each payroll country needs its own code.')

    @api.constrains('tax_year_start_month', 'tax_year_start_day')
    def _check_tax_year_start(self):
        for country in self:
            try:
                date(2001, country.tax_year_start_month, country.tax_year_start_day)
            except ValueError:
                raise ValidationError(_('%s: the tax year start is not a valid day.', country.name))

    def _tax_year_start(self, day):
        """First day of the tax year containing ``day``."""
        self.ensure_one()
        start = date(day.year, self.tax_year_start_month, self.tax_year_start_day)
        return start if start <= day else start.replace(year=day.year - 1)

    @api.model
    def _for_country(self, country):
        """The payroll country of a res.country, if its Payroll app is installed."""
        if not country:
            return self.browse()
        return self.search([('country_id', '=', country.id)], limit=1)

    @api.model
    def _default_for_company(self, company=None):
        company = company or self.env.company
        return self._for_country(company.country_id) or self.search([], limit=1)

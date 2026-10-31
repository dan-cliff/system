# -*- coding: utf-8 -*-
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# How a frequency's periods are measured. Code works out the period dates from
# these values, so they stay a fixed selection (see CLAUDE.md > Choice fields).
INTERVAL_UNITS = [
    ('week', 'Weeks'),
    ('semi_month', 'Half Months (1st – 15th, 16th – end)'),
    ('month', 'Months'),
]
# Weekly-based periods count from this date unless Settings say otherwise.
DEFAULT_PERIOD_START = date(2024, 1, 1)  # a Monday


class PayrollPayFrequency(models.Model):
    _name = 'payroll.pay.frequency'
    _description = 'Pay Frequency'
    _order = 'sequence, id'

    name = fields.Char(string='Pay Frequency', required=True, translate=True)
    code = fields.Char(string='Code', required=True, help='Technical code, e.g. WEEKLY.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    interval_unit = fields.Selection(INTERVAL_UNITS, string='Measured In', required=True, default='week')
    interval_count = fields.Integer(string='Every', required=True, default=1,
                                    help='How many weeks or months each pay period covers.')
    periods_per_year = fields.Integer(
        string='Pay Periods a Year', required=True, default=52,
        help='Used to turn annual salaries into pay and to annualise pay for tax tables (e.g. 52, 26, 24, 12).',
    )

    _code_unique = models.Constraint('UNIQUE(code)', 'Each pay frequency needs its own code.')

    @api.constrains('interval_count', 'periods_per_year')
    def _check_counts(self):
        for frequency in self:
            if frequency.interval_count < 1 or frequency.periods_per_year < 1:
                raise ValidationError(_('A pay frequency needs at least one period, and one period a year.'))

    @api.model
    def _period_anchor(self):
        value = self.env['ir.config_parameter'].sudo().get_param('advanced_payroll.period_start')
        try:
            return fields.Date.to_date(value) or DEFAULT_PERIOD_START
        except ValueError:
            return DEFAULT_PERIOD_START

    def _period_bounds(self, day):
        """First and last day of the pay period containing ``day``."""
        self.ensure_one()
        if self.interval_unit == 'semi_month':
            if day.day <= 15:
                return day.replace(day=1), day.replace(day=15)
            return day.replace(day=16), day + relativedelta(day=31)
        if self.interval_unit == 'month':
            months = (day.year * 12 + day.month - 1)
            start_index = months - months % self.interval_count
            start = date(start_index // 12, start_index % 12 + 1, 1)
            return start, start + relativedelta(months=self.interval_count, days=-1)
        length = 7 * self.interval_count
        anchor = self._period_anchor()
        start = anchor + timedelta(days=(day - anchor).days // length * length)
        return start, start + timedelta(days=length - 1)

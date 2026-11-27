# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollAuTaxScale(models.Model):
    """The ATO tax scale an employee is withheld at, from their TFN
    declaration."""
    _name = 'payroll.au.tax.scale'
    _description = 'Australian Tax Scale'
    _order = 'sequence, id'

    name = fields.Char(string='Tax Scale', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    tax_table_id = fields.Many2one('payroll.tax.table', string='Tax Table', required=True,
                                   domain="[('country_id.code', '=', 'AU')]")
    medicare_levy = fields.Boolean(string='Medicare Levy', default=True,
                                   help='Withhold the Medicare levy as well.')
    description = fields.Text(string='Description')

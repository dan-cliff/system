# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollCaProvince(models.Model):
    """A province or territory of employment and its income tax table."""
    _name = 'payroll.ca.province'
    _description = 'Canadian Province'
    _order = 'sequence, name, id'

    name = fields.Char(string='Province', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    state_id = fields.Many2one('res.country.state', string='State', domain="[('country_id.code', '=', 'CA')]")
    tax_table_id = fields.Many2one('payroll.tax.table', string='Tax Table', required=True,
                                   domain="[('country_id.code', '=', 'CA')]",
                                   help='Provincial brackets, with the basic personal amount as the Annual Credit Base.')
    description = fields.Text(string='Description')

# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollEmployee(models.Model):
    _inherit = 'payroll.employee'

    ca_sin = fields.Char(string='SIN', tracking=True)
    ca_province_id = fields.Many2one('payroll.ca.province', string='Province of Employment', tracking=True)
    ca_td1_federal = fields.Monetary(
        string='TD1 Federal Claim', tracking=True,
        help='Total claim amount from the federal TD1. Leave at 0 for the basic personal amount.',
    )
    ca_td1_provincial = fields.Monetary(
        string='TD1 Provincial Claim', tracking=True,
        help='Total claim amount from the provincial TD1. Leave at 0 for the basic personal amount.',
    )
    ca_cpp_exempt = fields.Boolean(string='CPP Exempt', tracking=True)
    ca_ei_exempt = fields.Boolean(string='EI Exempt', tracking=True)

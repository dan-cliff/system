# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollEmployee(models.Model):
    _inherit = 'payroll.employee'

    us_ssn = fields.Char(string='SSN', tracking=True)
    us_state_id = fields.Many2one('res.country.state', string='Work State', tracking=True,
                                  domain="[('country_id.code', '=', 'US')]")
    us_filing_status_id = fields.Many2one(
        'payroll.us.filing.status', string='Filing Status', tracking=True,
        default=lambda self: self.env.ref('advanced_payroll_us.filing_status_single', raise_if_not_found=False),
        help='W-4 Step 1(c).',
    )
    us_w4_step2 = fields.Boolean(string='Multiple Jobs (Step 2)', tracking=True,
                                 help='W-4 Step 2(c): two jobs, or married filing jointly with a working spouse.')
    us_w4_dependents = fields.Monetary(string='Dependents Credit (Step 3)', tracking=True,
                                       help='Annual amount claimed for dependents and other credits.')
    us_w4_other_income = fields.Monetary(string='Other Income (Step 4a)', tracking=True,
                                         help='Annual income from other sources to withhold for.')
    us_w4_deductions = fields.Monetary(string='Deductions (Step 4b)', tracking=True,
                                       help='Annual deductions above the standard deduction.')
    us_w4_extra_withholding = fields.Monetary(string='Extra Withholding (Step 4c)', tracking=True,
                                              help='Extra federal tax to withhold each pay period.')
    us_exempt = fields.Boolean(string='Exempt from Withholding', tracking=True,
                               help='The employee claimed exemption from federal income tax withholding.')

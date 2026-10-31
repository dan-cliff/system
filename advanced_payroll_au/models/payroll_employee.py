# -*- coding: utf-8 -*-
from odoo import fields, models


class PayrollEmployee(models.Model):
    _inherit = 'payroll.employee'

    au_tfn = fields.Char(string='Tax File Number', tracking=True)
    au_tax_scale_id = fields.Many2one(
        'payroll.au.tax.scale', string='Tax Scale', tracking=True,
        default=lambda self: self.env.ref('advanced_payroll_au.tax_scale_resident_threshold',
                                          raise_if_not_found=False),
        help='From the employee\'s TFN declaration.',
    )
    au_extra_withholding = fields.Monetary(string='Extra Withholding per Pay', tracking=True,
                                           help='Extra tax the employee asked to have withheld each pay.')
    au_super_fund = fields.Char(string='Super Fund', tracking=True)
    au_super_usi = fields.Char(string='Fund USI', tracking=True)
    au_super_member = fields.Char(string='Member Number', tracking=True)

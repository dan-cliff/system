# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PayrollEmployee(models.Model):
    _inherit = 'payroll.employee'

    nz_ird_number = fields.Char(string='IRD Number', tracking=True)
    nz_tax_code_id = fields.Many2one(
        'payroll.nz.tax.code', string='Tax Code', tracking=True,
        default=lambda self: self.env.ref('advanced_payroll_nz.tax_code_m', raise_if_not_found=False),
        help='From the employee\'s IR330 tax code declaration.',
    )
    nz_kiwisaver_member = fields.Boolean(string='KiwiSaver Member', default=True, tracking=True)
    nz_kiwisaver_rate = fields.Float(string='Employee Contribution (%)', default=3.5, tracking=True,
                                     help='3.5% by default from 1 April 2026; members can choose 4, 6, 8 or 10%.')
    nz_kiwisaver_employer_rate = fields.Float(string='Employer Contribution (%)', default=3.5, tracking=True)

    @api.constrains('nz_kiwisaver_rate', 'nz_kiwisaver_employer_rate')
    def _check_nz_kiwisaver(self):
        for profile in self:
            if min(profile.nz_kiwisaver_rate, profile.nz_kiwisaver_employer_rate) < 0:
                raise ValidationError(_('KiwiSaver rates cannot be negative.'))

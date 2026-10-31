# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PayrollEmployee(models.Model):
    _inherit = 'payroll.employee'

    # Follows the employee's Payroll Country (set from their Work Address).
    country_id = fields.Many2one(compute='_compute_country_id', store=True, readonly=False, precompute=True,
                                 default=None)

    @api.depends('employee_id.payroll_country_id')
    def _compute_country_id(self):
        for profile in self:
            country = profile.employee_id.sudo().payroll_country_id
            if country:
                profile.country_id = country
            elif not profile.country_id:
                profile.country_id = self.env['payroll.country']._default_for_company(profile.company_id)

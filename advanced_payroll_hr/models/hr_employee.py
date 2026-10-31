# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    payroll_country_id = fields.Many2one(
        'payroll.country', string='Payroll Country', groups='hr.group_hr_user',
        compute='_compute_payroll_country_id', store=True, readonly=False,
        help='Set from the country of the Work Address when that country\'s Payroll app is installed. '
             'Change it by hand if needed: it follows the Work Address again when the address changes.',
    )
    payroll_employee_ids = fields.One2many('payroll.employee', 'employee_id', string='Payroll Profiles',
                                           groups='advanced_payroll.group_payroll_user')
    payroll_employee_count = fields.Integer(compute='_compute_payroll_employee_count',
                                            groups='advanced_payroll.group_payroll_user')

    @api.depends('address_id.country_id')
    def _compute_payroll_country_id(self):
        PayrollCountry = self.env['payroll.country'].sudo()
        for employee in self:
            country = PayrollCountry._for_country(employee.address_id.country_id)
            if country:
                employee.payroll_country_id = country
            elif not employee.payroll_country_id:
                employee.payroll_country_id = PayrollCountry._default_for_company(employee.company_id)

    def _compute_payroll_employee_count(self):
        for employee in self:
            employee.payroll_employee_count = len(employee.payroll_employee_ids)

    def action_open_payroll_employee(self):
        """Open the employee's payroll profile in this company, adding it if
        there is none yet."""
        self.ensure_one()
        Profile = self.env['payroll.employee']
        profile = Profile.search([('employee_id', '=', self.id), ('company_id', '=', self.company_id.id)], limit=1)
        if not profile:
            if not Profile.has_access('create'):
                raise AccessError(_('You need a Payroll Employees permission that can create payroll employees.'))
            profile = Profile.create({'employee_id': self.id, 'company_id': self.company_id.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payroll Employee'),
            'res_model': 'payroll.employee',
            'res_id': profile.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

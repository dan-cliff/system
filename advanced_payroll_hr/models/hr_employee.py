# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Who sees the employee's pay (the Pay tab): the Payroll roles' permissions (the
# Payroll Employees ones, and approving or paying pay runs), not View My Payslips
# alone (Payroll – Employee). Whether they can change it follows their access to
# the payroll details record (payroll_readonly).
PAYROLL_EMPLOYEE_GROUPS = ','.join([f'advanced_payroll.group_employee_{perm}' for perm in (
    'create_only', 'edit_own', 'edit_team', 'edit_all', 'view_all', 'delete_own', 'delete_all')]
    + ['advanced_payroll.group_run_approve', 'advanced_payroll.group_run_pay'])
# Employee fields kept on the payroll profile: {employee field: payroll.employee field}.
PROFILE_FIELDS = {
    'payroll_pay_frequency_id': 'pay_frequency_id',
    'payroll_pay_basis': 'pay_basis',
    'payroll_annual_salary': 'annual_salary',
    'payroll_hourly_rate': 'hourly_rate',
    'payroll_hours_per_week': 'hours_per_week',
    'payroll_date_start': 'date_start',
    'payroll_date_end': 'date_end',
}


class HrEmployee(models.Model):
    """With Personnel switched on, payroll is kept on the employee: the payroll
    profile (payroll.employee) becomes the employee's payroll details record,
    edited from the employee's Pay tab, and Payroll › Employees opens Personnel
    employees."""
    _inherit = 'hr.employee'

    payroll_country_id = fields.Many2one(
        'payroll.country', string='Payroll Country', groups='hr.group_hr_user',
        compute='_compute_payroll_country_id', store=True, readonly=False,
        help='Set from the country of the Work Address when that country\'s Payroll app is installed. '
             'Change it by hand if needed: it follows the Work Address again when the address changes.',
    )
    payroll_employee_ids = fields.One2many('payroll.employee', 'employee_id', string='Payroll Details',
                                           groups=PAYROLL_EMPLOYEE_GROUPS)
    payroll_employee_id = fields.Many2one(
        'payroll.employee', string='Payroll Details', compute='_compute_payroll_employee_id',
        groups=PAYROLL_EMPLOYEE_GROUPS,
        help='The employee\'s payroll details in their company.',
    )
    payroll_active = fields.Boolean(
        string='In Payroll', compute='_compute_payroll_employee_id', inverse='_inverse_payroll_active',
        search='_search_payroll_active', groups=PAYROLL_EMPLOYEE_GROUPS,
        help='Paid by Payroll: the employee gets a payslip in the pay runs of their Payroll Country and '
             'Pay Frequency.',
    )
    payroll_currency_id = fields.Many2one(related='company_id.currency_id', string='Payroll Currency')
    payroll_pay_frequency_id = fields.Many2one(
        'payroll.pay.frequency', string='Pay Frequency', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_pay_basis = fields.Selection(
        [('salary', 'Annual Salary'), ('hourly', 'Hourly Rate')], string='Paid By', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_annual_salary = fields.Monetary(
        string='Annual Salary', currency_field='payroll_currency_id', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_hourly_rate = fields.Monetary(
        string='Hourly Rate', currency_field='payroll_currency_id', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields',
        help='For salaried employees: the annual salary over 52 weeks of standard hours.')
    payroll_hours_per_week = fields.Float(
        string='Standard Hours a Week', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_date_start = fields.Date(
        string='Paid From', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_date_end = fields.Date(
        string='Paid Until', groups=PAYROLL_EMPLOYEE_GROUPS,
        compute='_compute_payroll_profile_fields', inverse='_inverse_payroll_profile_fields')
    payroll_slip_count = fields.Integer(compute='_compute_payroll_slip_count', groups=PAYROLL_EMPLOYEE_GROUPS)
    payroll_readonly = fields.Boolean(compute='_compute_payroll_readonly', groups=PAYROLL_EMPLOYEE_GROUPS,
                                      help='The current user can see this employee\'s pay but not change it.')

    @api.depends('address_id.country_id')
    def _compute_payroll_country_id(self):
        PayrollCountry = self.env['payroll.country'].sudo()
        for employee in self:
            country = PayrollCountry._for_country(employee.address_id.country_id)
            if country:
                employee.payroll_country_id = country
            elif not employee.payroll_country_id:
                employee.payroll_country_id = PayrollCountry._default_for_company(employee.company_id)

    # ------------------------------------------------------------------
    # The payroll details record (payroll.employee) of the employee's company
    # ------------------------------------------------------------------
    def _payroll_profile(self, active_test=True):
        self.ensure_one()
        if not self.id:
            return self.env['payroll.employee']
        return self.env['payroll.employee'].with_context(active_test=active_test).search([
            ('employee_id', '=', self.id), ('company_id', '=', self.company_id.id)], limit=1)

    def _payroll_ensure_profile(self):
        """The employee's payroll details, added (or brought back) if needed."""
        self.ensure_one()
        profile = self._payroll_profile(active_test=False)
        if profile:
            if not profile.active:
                profile.active = True
            return profile
        Profile = self.env['payroll.employee']
        if not Profile.has_access('create'):
            raise AccessError(_('You need a Payroll Employees permission that can create payroll employees '
                                'to add %s to Payroll.', self.name))
        if not self.sudo().payroll_country_id:
            raise UserError(_('Set the Payroll Country of %s first (it follows the Work Address).', self.name))
        return Profile.create({'employee_id': self.id, 'company_id': self.company_id.id})

    @api.depends('payroll_employee_ids.active', 'payroll_employee_ids.company_id', 'company_id')
    def _compute_payroll_employee_id(self):
        for employee in self:
            profile = employee._payroll_profile()
            employee.payroll_employee_id = profile
            employee.payroll_active = bool(profile)

    def _inverse_payroll_active(self):
        for employee in self:
            if employee.payroll_active:
                employee._payroll_ensure_profile()
            else:
                employee._payroll_profile().write({'active': False})

    def _search_payroll_active(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        profiles = self.env['payroll.employee'].search([])
        employee_ids = [p.employee_id.id for p in profiles if p.company_id == p.employee_id.company_id]
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', employee_ids)]

    @api.depends(*(f'payroll_employee_ids.{name}' for name in PROFILE_FIELDS.values()))
    def _compute_payroll_profile_fields(self):
        for employee in self:
            profile = employee._payroll_profile()
            for field, profile_field in PROFILE_FIELDS.items():
                employee[field] = profile[profile_field] if profile else False

    def _inverse_payroll_profile_fields(self):
        for employee in self:
            profile = employee._payroll_profile()
            # Only what changed: writing a value also stops the profile recomputing
            # it (e.g. a salaried employee's hourly rate after a new salary).
            vals = {}
            for field, profile_field in PROFILE_FIELDS.items():
                value = employee[field]
                if (value != profile[profile_field]) if profile else bool(value):
                    vals[profile_field] = value.id if isinstance(value, models.BaseModel) else value
            if vals:
                (profile or employee._payroll_ensure_profile()).write(vals)

    @api.depends('payroll_employee_ids')
    @api.depends_context('uid')
    def _compute_payroll_readonly(self):
        can_create = self.env['payroll.employee'].has_access('create')
        for employee in self:
            profile = employee._payroll_profile(active_test=False)
            employee.payroll_readonly = not (profile.has_access('write') if profile else can_create)

    def _compute_payroll_slip_count(self):
        counts = dict(self.env['payroll.slip']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count']))
        for employee in self:
            employee.payroll_slip_count = counts.get(employee, 0)

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_open_payroll_employee(self):
        """The employee's country tax details (and the rest of their payroll
        details), in a dialog."""
        self.ensure_one()
        profile = self._payroll_ensure_profile()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payroll Details: %s', self.name),
            'res_model': 'payroll.employee',
            'res_id': profile.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_open_payroll_slips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips'),
            'res_model': 'payroll.slip',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'create': False},
        }

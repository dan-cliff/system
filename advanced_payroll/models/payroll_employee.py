# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PayrollEmployee(models.Model):
    """An employee's payroll profile. Country apps add the country's own
    details (tax numbers, tax codes, retirement funds) with _inherit and show
    them on a page of the form for their country code."""
    _name = 'payroll.employee'
    _description = 'Payroll Employee'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, id'
    # The profile takes its Organisation units from the employee (org_structure).
    _org_parent_field = 'employee_id'

    name = fields.Char(related='employee_id.name', string='Name', store=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, index=True, tracking=True,
                                  domain="[('company_id', 'in', allowed_company_ids)]")
    user_id = fields.Many2one(related='employee_id.user_id', string='User', store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, tracking=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    country_id = fields.Many2one(
        'payroll.country', string='Payroll Country', required=True, index=True, tracking=True,
        default=lambda self: self.env['payroll.country']._default_for_company(),
        help='Which country\'s payroll rules apply. With Personnel switched on (Settings › Payroll) it '
             'follows the employee\'s Work Address.',
    )
    country_code = fields.Char(related='country_id.code', string='Country Code')
    pay_frequency_id = fields.Many2one(
        'payroll.pay.frequency', string='Pay Frequency', required=True, tracking=True,
        compute='_compute_pay_frequency_id', store=True, readonly=False, precompute=True,
    )
    pay_basis = fields.Selection(
        [('salary', 'Annual Salary'), ('hourly', 'Hourly Rate')],
        string='Paid By', required=True, default='salary', tracking=True,
        help='Salaried employees get their salary each period; hourly employees are paid for the hours '
             'worked (standard hours, or hours from the app chosen in Settings › Payroll › Pay Hours From).',
    )
    annual_salary = fields.Monetary(string='Annual Salary', tracking=True)
    hourly_rate = fields.Monetary(
        string='Hourly Rate', tracking=True,
        compute='_compute_hourly_rate', store=True, readonly=False,
        help='For salaried employees: the annual salary over 52 weeks of standard hours.',
    )
    hours_per_week = fields.Float(
        string='Standard Hours a Week', tracking=True,
        compute='_compute_hours_per_week', store=True, readonly=False, precompute=True,
    )
    date_start = fields.Date(string='Paid From', tracking=True,
                             help='First day this employee is paid. Leave empty to pay them on every pay run.')
    date_end = fields.Date(string='Paid Until', tracking=True,
                           help='Last day this employee is paid, e.g. their last day of work.')
    slip_ids = fields.One2many('payroll.slip', 'payroll_employee_id', string='Payslips')
    slip_count = fields.Integer(compute='_compute_slip_count', string='Payslips')
    note = fields.Html(string='Notes')

    _employee_company_unique = models.Constraint(
        'UNIQUE(employee_id, company_id)', 'An employee can only have one payroll profile per company.')

    @api.depends('country_id')
    def _compute_pay_frequency_id(self):
        for profile in self:
            if not profile.pay_frequency_id and profile.country_id.default_pay_frequency_id:
                profile.pay_frequency_id = profile.country_id.default_pay_frequency_id

    @api.depends('country_id')
    def _compute_hours_per_week(self):
        for profile in self:
            if not profile.hours_per_week:
                profile.hours_per_week = profile.country_id.standard_hours_per_week or 38.0

    @api.depends('pay_basis', 'annual_salary', 'hours_per_week')
    def _compute_hourly_rate(self):
        for profile in self:
            if profile.pay_basis == 'salary' and profile.hours_per_week:
                profile.hourly_rate = profile.currency_id.round(profile.annual_salary / (52 * profile.hours_per_week))

    def _compute_slip_count(self):
        counts = dict(self.env['payroll.slip']._read_group(
            [('payroll_employee_id', 'in', self.ids)], ['payroll_employee_id'], ['__count']))
        for profile in self:
            profile.slip_count = counts.get(profile, 0)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for profile in self:
            if profile.date_start and profile.date_end and profile.date_end < profile.date_start:
                raise ValidationError(_('%s: Paid Until cannot be before Paid From.', profile.name))

    @api.constrains('annual_salary', 'hourly_rate', 'hours_per_week')
    def _check_amounts(self):
        for profile in self:
            if min(profile.annual_salary, profile.hourly_rate, profile.hours_per_week) < 0:
                raise ValidationError(_('%s: pay and hours cannot be negative.', profile.name))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id.company_id:
            self.company_id = self.employee_id.company_id

    def _ordinary_pay_item(self):
        self.ensure_one()
        return self.country_id.ordinary_pay_item_id or self.env.ref('advanced_payroll.pay_item_ordinary')

    def _rate_for(self, pay_item, multiplier=1.0):
        """Hourly rate of a pay item for this employee."""
        self.ensure_one()
        return self.hourly_rate * (pay_item.rate_multiplier or 1.0) * multiplier

    def action_open_slips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips'),
            'res_model': 'payroll.slip',
            'view_mode': 'list,form',
            'domain': [('payroll_employee_id', '=', self.id)],
            'context': {'create': False},
        }

# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.advanced_rostering.models.rostering_tools import search_positive


class RosteringLeave(models.Model):
    _inherit = 'rostering.leave'
    # The request takes its Organisation units from the employee (org_structure),
    # follows them when the employee changes, and keeps them off the form.
    _org_parent_field = 'employee_id'
    _org_form_section = False

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', index=True, tracking=True,
        default=lambda self: self.env.user.employee_id,
        domain="[('company_id', 'in', [company_id, False])]",
        context={'rostering_employee_picker': True},
    )
    manager_id = fields.Many2one(related='employee_id.parent_id', string='Manager')
    # Follows the employee; default=None drops the base module's "current user" default.
    user_id = fields.Many2one(compute='_compute_user_id', store=True, readonly=False, precompute=True,
                              default=None)
    in_my_team = fields.Boolean(string='My Team', compute='_compute_in_my_team', search='_search_in_my_team')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Requested for a user: their employee, not the default (the current user's).
            if vals.get('user_id') and 'employee_id' not in vals:
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['employee_id'] = self.env['res.users'].browse(vals['user_id']).with_company(company).employee_id.id
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals:
            vals = dict(vals, **self._org_values_from_employee(vals['employee_id']))
        return super().write(vals)

    @api.model
    def _org_values_from_employee(self, employee_id):
        """The employee's Organisation units, for the leave to follow
        (nothing when Organisation Structure is not installed)."""
        if 'org_division_id' not in self._fields or not hasattr(self, '_org_values_from_parent'):
            return {}
        if not employee_id:
            return {}
        return self._org_values_from_parent(employee_id)

    def _sync_org_from_employee(self):
        for leave in self.filtered('employee_id'):
            values = self._org_values_from_employee(leave.employee_id.id)
            if values and any(leave[name].id != value for name, value in values.items()):
                super(RosteringLeave, leave).write(values)

    @api.model
    def _person_field(self):
        return 'employee_id'

    @api.model
    def _person_fields(self):
        return super()._person_fields() + ['employee_id']

    @api.model
    def _my_domain(self):
        return ['|', ('employee_id', 'in', self.env.user.employee_ids.ids), ('user_id', '=', self.env.uid)]

    def _person_users(self):
        return self.employee_id.user_id | super()._person_users()

    def _may_request_for(self):
        """Managers with Create and Edit My Team request leave for everyone
        under them in the org chart."""
        return super()._may_request_for() or (
            self.env.user.has_group('advanced_rostering.group_leave_edit_team')
            and self.filtered_domain(self._search_in_my_team('in', [True]))
        )

    @api.depends('employee_id')
    def _compute_user_id(self):
        for leave in self:
            if leave.employee_id:
                leave.user_id = leave.employee_id.user_id
            elif not leave.user_id:
                leave.user_id = self.env.user

    @api.depends('employee_id.name')
    def _compute_person_name(self):
        super()._compute_person_name()
        for leave in self.filtered('employee_id'):
            leave.person_name = leave.employee_id.name

    @api.depends('employee_id.parent_id.user_id')
    def _compute_approver_user_id(self):
        for leave in self:
            leave.approver_user_id = leave.employee_id.parent_id.user_id

    def _get_tz(self):
        self.ensure_one()
        return self.employee_id.tz or super()._get_tz()

    def _full_day_hours(self):
        """A whole day off is a full-time day of the company's working hours
        (Personnel settings): its Full Time Equivalent hours per week, over the
        days the schedule works (e.g. 38 hours / 5 days = 7.6)."""
        self.ensure_one()
        calendar = (self.company_id or self.env.company).sudo().resource_calendar_id
        if calendar.full_time_required_hours and calendar.hours_per_week and calendar.hours_per_day:
            return calendar.full_time_required_hours * calendar.hours_per_day / calendar.hours_per_week
        return calendar.hours_per_day or super()._full_day_hours()

    def _holiday_jurisdictions(self):
        self.ensure_one()
        jurisdictions = self.employee_id.sudo().rostering_holiday_jurisdiction_ids
        if jurisdictions and self.env['hr.employee']._rostering_jurisdictions_switched_on():
            return jurisdictions
        return super()._holiday_jurisdictions()

    @api.depends('employee_id')
    def _compute_hours(self):
        return super()._compute_hours()

    @api.depends('date_from', 'date_to', 'employee_id')
    def _compute_shift_ids(self):
        return super()._compute_shift_ids()

    @api.depends_context('uid')
    def _compute_in_my_team(self):
        team = self.filtered_domain(self._search_in_my_team('in', [True]))
        for leave in self:
            leave.in_my_team = leave in team

    def _search_in_my_team(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = [('employee_id', 'child_of', self.env.user.employee_ids.ids)]
        if positive:
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    @api.constrains('employee_id')
    def _check_employee_overlap(self):
        self._check_overlap()

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id.company_id:
            self.company_id = self.employee_id.company_id

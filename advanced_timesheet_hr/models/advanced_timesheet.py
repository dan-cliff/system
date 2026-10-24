# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdvancedTimesheet(models.Model):
    _inherit = 'advanced.timesheet'
    # The timesheet takes its Organisation units from the employee (org_structure).
    _org_parent_field = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', index=True, tracking=True,
        default=lambda self: self.env.user.employee_id,
        domain="[('company_id', 'in', allowed_company_ids)]",
    )
    # Follows the employee; default=None drops the base module's "current user" default.
    user_id = fields.Many2one(compute='_compute_user_id', store=True, readonly=False, precompute=True,
                              default=None)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Created for a user: their employee, not the default (the current user's).
            if vals.get('user_id') and 'employee_id' not in vals:
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['employee_id'] = self.env['res.users'].browse(vals['user_id']).with_company(company).employee_id.id
        return super().create(vals_list)

    @api.model
    def _approval_required(self):
        return self.env['ir.config_parameter'].sudo().get_param('advanced_timesheet.manager_approval') == 'True'

    @api.model
    def _person_field_names(self):
        return super()._person_field_names() + ['employee_id']

    @api.model
    def _person_domain_from_vals(self, vals):
        if vals.get('employee_id'):
            return [('employee_id', '=', vals['employee_id'])]
        return super()._person_domain_from_vals(vals)

    def _person_vals(self):
        self.ensure_one()
        if self.employee_id:
            return {'employee_id': self.employee_id.id}
        return super()._person_vals()

    @api.model
    def _default_person_vals(self):
        employee = self.env.user.employee_id
        if employee:
            return {'employee_id': employee.id}
        return super()._default_person_vals()

    @api.depends('employee_id')
    def _compute_user_id(self):
        for sheet in self:
            if sheet.employee_id:
                sheet.user_id = sheet.employee_id.user_id
            elif not sheet.user_id:
                sheet.user_id = self.env.user

    @api.depends('employee_id.name')
    def _compute_person_name(self):
        super()._compute_person_name()
        for sheet in self.filtered('employee_id'):
            sheet.person_name = sheet.employee_id.name

    @api.depends('employee_id.parent_id.user_id')
    def _compute_approver_user_id(self):
        for sheet in self:
            sheet.approver_user_id = sheet.employee_id.parent_id.user_id

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id.company_id:
            self.company_id = self.employee_id.company_id

    @api.constrains('employee_id')
    def _check_employee_dates(self):
        self._check_dates()

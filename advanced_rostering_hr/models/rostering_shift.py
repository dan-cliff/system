# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.advanced_rostering.models.rostering_tools import search_positive


class RosteringShift(models.Model):
    _inherit = 'rostering.shift'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', index=True,
        domain="[('company_id', 'in', [company_id, False])]",
        context={'rostering_employee_picker': True},
        help='Leave empty for an open shift to assign later.',
    )
    manager_id = fields.Many2one(related='employee_id.parent_id', string='Manager')
    # Follows the employee.
    user_id = fields.Many2one(compute='_compute_user_id', store=True, readonly=False, precompute=True)
    in_my_team = fields.Boolean(string='My Team', compute='_compute_in_my_team', search='_search_in_my_team')

    @api.model
    def _person_field(self):
        return 'employee_id'

    @api.model
    def _my_domain(self):
        return ['|', ('employee_id', 'in', self.env.user.employee_ids.ids), ('user_id', '=', self.env.uid)]

    def _get_tz(self):
        self.ensure_one()
        return self.employee_id.tz or super()._get_tz()

    @api.depends('employee_id')
    def _compute_user_id(self):
        for shift in self:
            shift.user_id = shift.employee_id.user_id

    @api.depends('employee_id.name')
    def _compute_person_name(self):
        super()._compute_person_name()
        for shift in self.filtered('employee_id'):
            shift.person_name = shift.employee_id.name
            shift.is_assigned = True

    @api.depends('employee_id.tz')
    def _compute_datetimes(self):
        return super()._compute_datetimes()

    @api.depends_context('uid')
    def _compute_in_my_team(self):
        team = self.filtered_domain(self._search_in_my_team('in', [True]))
        for shift in self:
            shift.in_my_team = shift in team

    def _search_in_my_team(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = [('employee_id', 'child_of', self.env.user.employee_ids.ids)]
        if positive:
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    def _holiday_jurisdictions(self):
        # The employee's own jurisdictions when Settings › Rostering gives
        # employees theirs; otherwise (or when they have none) the company's.
        self.ensure_one()
        if self.employee_id.rostering_holiday_jurisdiction_ids and \
                self.env['hr.employee']._rostering_jurisdictions_switched_on():
            return self.employee_id.sudo().rostering_holiday_jurisdiction_ids
        return super()._holiday_jurisdictions()

    def _all_holiday_jurisdictions(self):
        jurisdictions = super()._all_holiday_jurisdictions()
        if self.env['hr.employee']._rostering_jurisdictions_switched_on():
            jurisdictions |= self.employee_id.sudo().rostering_holiday_jurisdiction_ids
        return jurisdictions

    @api.model
    def _my_holiday_jurisdictions(self):
        employee = self.env.user.employee_id
        if employee and self.env['hr.employee']._rostering_jurisdictions_switched_on() \
                and employee.sudo().rostering_holiday_jurisdiction_ids:
            return employee.sudo().rostering_holiday_jurisdiction_ids
        return super()._my_holiday_jurisdictions()

    @api.depends('employee_id')
    def _compute_public_holiday(self):
        return super()._compute_public_holiday()

    @api.model
    def _my_person_name(self):
        return self.env.user.employee_id.name or super()._my_person_name()

    @api.model
    def _my_manager_name(self):
        return self.env.user.employee_id.parent_id.name or False

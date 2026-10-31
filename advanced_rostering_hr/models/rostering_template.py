# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RosteringTemplateLine(models.Model):
    _inherit = 'rostering.template.line'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', index=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        context={'rostering_employee_picker': True},
        help='Leave empty for a shift to assign later.',
    )
    # Follows the employee.
    user_id = fields.Many2one(compute='_compute_user_id', store=True, readonly=False, precompute=True)

    @api.depends('employee_id')
    def _compute_user_id(self):
        for line in self:
            line.user_id = line.employee_id.user_id

    @api.depends('employee_id.name')
    def _compute_person_name(self):
        super()._compute_person_name()
        for line in self.filtered('employee_id'):
            line.person_name = line.employee_id.name

    def _prepare_shift_vals(self, roster, day):
        vals = super()._prepare_shift_vals(roster, day)
        vals['employee_id'] = self.employee_id.id
        return vals

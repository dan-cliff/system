from odoo import models, fields, api, _


class HrEmployeeExt(models.Model):
    _inherit = 'hr.employee'

    lms_record_ids = fields.One2many(
        'lms.employee.record', 'employee_id', string='Training Records'
    )
    lms_record_count = fields.Integer(
        string='Training Records', compute='_compute_lms_record_count'
    )
    lms_assignment_ids = fields.One2many(
        'lms.course.group.assignment', 'employee_id', string='Training Packages'
    )
    lms_assignment_count = fields.Integer(
        string='Training Packages', compute='_compute_lms_assignment_count'
    )
    lms_enrollment_ids = fields.One2many(
        'lms.session.enrollment', 'employee_id', string='Session Enrolments'
    )

    def _compute_lms_record_count(self):
        for emp in self:
            emp.lms_record_count = len(emp.lms_record_ids)

    def _compute_lms_assignment_count(self):
        for emp in self:
            emp.lms_assignment_count = len(emp.lms_assignment_ids)

    def action_view_lms_records(self):
        self.ensure_one()
        return {
            'name': _('Training Records — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.employee.record',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_lms_assignments(self):
        self.ensure_one()
        return {
            'name': _('Training Packages — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.course.group.assignment',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

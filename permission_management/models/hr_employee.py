from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for employee in employees:
            if (
                employee.user_id
                and employee.job_id
                and employee.job_id.default_permission_profile_id
                and not employee.user_id.permission_profile_override
            ):
                employee.user_id.with_context(auto_profile_sync=True).write({
                    'permission_profile_id': employee.job_id.default_permission_profile_id.id,
                    'permission_profile_override': False,
                })
        return employees

    def write(self, vals):
        result = super().write(vals)
        if 'job_id' in vals or 'user_id' in vals:
            for employee in self:
                if (
                    employee.user_id
                    and employee.job_id
                    and employee.job_id.default_permission_profile_id
                    and not employee.user_id.permission_profile_override
                ):
                    employee.user_id.with_context(auto_profile_sync=True).write({
                        'permission_profile_id': employee.job_id.default_permission_profile_id.id,
                        'permission_profile_override': False,
                    })
        return result

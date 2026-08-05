from odoo import api, fields, models


class EmployeeHealthcareAlert(models.Model):
    _name = 'employee.healthcare.alert'
    _description = 'Employee Health Alert'
    _order = 'healthcare_id, date_noted desc'

    healthcare_id = fields.Many2one(
        'employee.healthcare',
        string='Healthcare Record',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Stored related so security rule domains ([('employee_id.user_id', '=', user.id)]) work
    employee_id = fields.Many2one(
        'hr.employee',
        related='healthcare_id.employee_id',
        store=True,
        string='Employee',
    )
    alert_type_id = fields.Many2one(
        'employee.healthcare.alert.type',
        string='Alert Type',
    )
    alert_severity_id = fields.Many2one(
        'employee.healthcare.alert.severity',
        string='Alert Severity',
    )
    alert_severity_color = fields.Integer(
        related='alert_severity_id.color',
        string='Alert Severity Colour',
        store=False,
    )
    description = fields.Text(string='Description', required=True)
    date_noted = fields.Date(string='Date Noted')
    is_critical = fields.Boolean(string='Critical', default=False)
    action_plan = fields.Binary(
        string='Health / Action Plan',
        attachment=True,
    )
    action_plan_filename = fields.Char(string='Health / Action Plan Filename')

    def _reeval_employee(self):
        self.mapped('healthcare_id').action_evaluate_healthcare_indicators()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._reeval_employee()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._reeval_employee()
        return result

    def unlink(self):
        healthcare_ids = self.mapped('healthcare_id')
        result = super().unlink()
        healthcare_ids.action_evaluate_healthcare_indicators()
        return result

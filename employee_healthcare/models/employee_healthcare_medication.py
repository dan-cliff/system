from odoo import api, fields, models


class EmployeeHealthcareMedication(models.Model):
    _name = 'employee.healthcare.medication'
    _description = 'Employee Medication'
    _order = 'healthcare_id, name'

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
    name = fields.Char(string='Medication Name', required=True)
    medication_type_id = fields.Many2one(
        'employee.healthcare.medication.type',
        string='Medication Type',
    )
    dosage = fields.Char(string='Dosage')
    frequency_id = fields.Many2one(
        'employee.healthcare.medication.frequency',
        string='Frequency',
    )
    prescribing_doctor = fields.Char(string='Prescribing Doctor')
    notes = fields.Text(string='Notes')

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

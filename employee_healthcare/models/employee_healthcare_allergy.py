from odoo import api, fields, models


class EmployeeHealthcareAllergy(models.Model):
    _name = 'employee.healthcare.allergy'
    _description = 'Employee Allergy'
    _order = 'healthcare_id, allergen'

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
    allergen = fields.Char(string='Allergen', required=True)
    allergy_type_id = fields.Many2one(
        'employee.healthcare.allergy.type',
        string='Allergy Type',
    )
    severity_id = fields.Many2one(
        'employee.healthcare.allergy.severity',
        string='Severity',
    )
    severity_color = fields.Integer(
        related='severity_id.color',
        string='Severity Colour',
        store=False,
    )
    reaction = fields.Text(string='Reaction / Symptoms')
    treatment = fields.Text(string='Treatment / Management')

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

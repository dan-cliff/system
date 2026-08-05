from odoo import api, fields, models


class EmployeeHealthcareDirective(models.Model):
    _name = 'employee.healthcare.directive'
    _description = 'Advanced Directive / Medical Decision-Making Proxy'
    _order = 'healthcare_id, directive_type_id, name'

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
    directive_type_id = fields.Many2one(
        'employee.healthcare.directive.type',
        string='Directive Type',
        required=True,
    )
    name = fields.Char(
        string='Document Title / Person Name',
        required=True,
        help='For proxy records, enter the proxy person\'s full name. '
             'For document directives, enter the document title.',
    )
    relationship = fields.Char(
        string='Relationship',
        help='Relationship to the employee (for proxy/decision-maker records).',
    )
    phone = fields.Char(
        string='Contact Phone',
        help='Contact phone number for the proxy or decision-maker.',
    )
    email = fields.Char(
        string='Contact Email',
    )
    date_executed = fields.Date(
        string='Date Executed',
        help='Date the directive was signed or executed.',
    )
    document = fields.Binary(string='Document', attachment=True)
    document_filename = fields.Char(string='Document Filename')
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

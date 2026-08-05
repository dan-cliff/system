from odoo import fields, models


class EmployeeHealthcareMedicationType(models.Model):
    _name = 'employee.healthcare.medication.type'
    _description = 'Medication Type'
    _order = 'name'

    name = fields.Char(string='Medication Type', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Medication type name must be unique.')


class EmployeeHealthcareMedicationFrequency(models.Model):
    _name = 'employee.healthcare.medication.frequency'
    _description = 'Medication Frequency'
    _order = 'name'

    name = fields.Char(string='Frequency', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Frequency name must be unique.')


class EmployeeHealthcareAllergyType(models.Model):
    _name = 'employee.healthcare.allergy.type'
    _description = 'Allergy Type'
    _order = 'name'

    name = fields.Char(string='Allergy Type', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Allergy type name must be unique.')


class EmployeeHealthcareAllergySeverity(models.Model):
    _name = 'employee.healthcare.allergy.severity'
    _description = 'Allergy Severity'
    _order = 'sequence, name'

    name = fields.Char(string='Severity', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Colour', default=0)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Severity name must be unique.')


class EmployeeHealthcareAlertType(models.Model):
    _name = 'employee.healthcare.alert.type'
    _description = 'Health Alert Type'
    _order = 'name'

    name = fields.Char(string='Alert Type', required=True, translate=True)
    months_to_review = fields.Integer(
        string='Months to Review',
        default=0,
        help='Number of months after which an alert of this type should be reviewed. '
             'Zero means no scheduled review.',
    )
    require_care_plan = fields.Boolean(
        string='Require Care Plan',
        default=False,
        help='When checked, employees with an alert of this type must have a care plan on file.',
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Alert type name must be unique.')


class EmployeeHealthcareDirectiveType(models.Model):
    _name = 'employee.healthcare.directive.type'
    _description = 'Directive / Proxy Type'
    _order = 'name'

    name = fields.Char(string='Directive Type', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Directive type name must be unique.')


class EmployeeHealthcareInsurer(models.Model):
    _name = 'employee.healthcare.insurer'
    _description = 'Private Health Insurer'
    _order = 'name'

    name = fields.Char(string='Insurer Name', required=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Insurer name must be unique.')


class EmployeeHealthcareAmbulanceProvider(models.Model):
    _name = 'employee.healthcare.ambulance.provider'
    _description = 'Ambulance Membership Provider'
    _order = 'name'

    name = fields.Char(string='Provider Name', required=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Provider name must be unique.')


class EmployeeHealthcareAlertSeverity(models.Model):
    _name = 'employee.healthcare.alert.severity'
    _description = 'Health Alert Severity'
    _order = 'sequence, name'

    name = fields.Char(string='Alert Severity', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Colour', default=0)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Alert severity name must be unique.')

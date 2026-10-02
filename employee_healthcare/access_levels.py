"""Employee Healthcare access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py employee_healthcare
"""

APP_NAME = 'Employee Healthcare'
PREFIX = 'hc'
CATEGORY = 'module_category_employee_healthcare'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_EMPLOYEE = ['employee_id.user_id']

MODELS = [
    ('record', 'Healthcare Records', OPERATIONAL, ['model_employee_healthcare'], _EMPLOYEE),
    ('medication', 'Medications', OPERATIONAL, ['model_employee_healthcare_medication'], _EMPLOYEE),
    ('allergy', 'Allergies', OPERATIONAL, ['model_employee_healthcare_allergy'], _EMPLOYEE),
    ('alert', 'Health Alerts', OPERATIONAL, ['model_employee_healthcare_alert'], _EMPLOYEE),
    ('directive', 'Advanced Directives', OPERATIONAL, ['model_employee_healthcare_directive'], _EMPLOYEE),
    ('indicator', 'Healthcare Indicators', CONFIG,
     ['model_employee_healthcare_indicator', 'model_employee_healthcare_indicator_rule'], []),
    ('medication_type', 'Medication Types', CONFIG, ['model_employee_healthcare_medication_type'], []),
    ('medication_frequency', 'Medication Frequencies', CONFIG,
     ['model_employee_healthcare_medication_frequency'], []),
    ('allergy_type', 'Allergy Types', CONFIG, ['model_employee_healthcare_allergy_type'], []),
    ('allergy_severity', 'Allergy Severities', CONFIG, ['model_employee_healthcare_allergy_severity'], []),
    ('alert_type', 'Health Alert Types', CONFIG, ['model_employee_healthcare_alert_type'], []),
    ('alert_severity', 'Health Alert Severities', CONFIG, ['model_employee_healthcare_alert_severity'], []),
    ('directive_type', 'Directive / Proxy Types', CONFIG, ['model_employee_healthcare_directive_type'], []),
    ('insurer', 'Private Health Insurers', CONFIG, ['model_employee_healthcare_insurer'], []),
    ('ambulance_provider', 'Ambulance Providers', CONFIG, ['model_employee_healthcare_ambulance_provider'], []),
]

# The healthcare tab writes to the employee record (as before this module moved to access levels).
EXTRA_ACCESS = [
    ('access_hr_employee_healthcare_record', 'hr.model_hr_employee', 'group_hc_record_view', 'rw'),
]

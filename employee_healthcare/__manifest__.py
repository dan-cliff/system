{
    'name': 'Employee Healthcare',
    'version': '19.0.1.1.0',
    'summary': 'Employee healthcare information management',
    'description': (
        'Allows employees to record and manage their personal healthcare information, '
        'including Medicare details, health alerts, medications, allergies, '
        'private health insurance, ambulance memberships, and advanced directives / '
        'medical decision-making proxies. Includes a configurable indicator system '
        'and a printable Care Profile PDF report.'
    ),
    'category': 'Human Resources',
    'author': 'Custom',
    'depends': ['hr', 'mail'],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/res_lang_data.xml',
        'data/employee_healthcare_data.xml',
        'data/employee_healthcare_onboarding.xml',
        'views/employee_healthcare_config_views.xml',
        'views/employee_healthcare_child_views.xml',
        'views/hr_employee_views.xml',
        'report/employee_care_profile_report.xml',
        'views/employee_healthcare_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'employee_healthcare/static/src/js/employee_healthcare_form.js',
            'employee_healthcare/static/src/js/month_year_field.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'images': ['static/description/icon.png'],
}

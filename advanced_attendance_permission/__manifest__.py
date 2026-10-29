{
    'name': 'On Site - Permission Management',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Standard Permission Management roles for On Site',
    'description': """
        Installs automatically when both On Site and Permission Management are
        installed, and adds these roles:

        - On Site – Administrator: everything, including deleting any attendance,
          kiosk or alert, signing in from Odoo, approving extra hours and Configuration
        - On Site – Manager: create and edit their own and their team's attendances,
          kiosks and alerts, sign in from Odoo; no deleting
        - On Site – Employee: create and edit their own attendances and alerts,
          sign in from Odoo; no deleting
        - On Site – Extra Hours Approver: approve or refuse extra hours
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_attendance', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

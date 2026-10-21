{
    'name': 'SCORM Authoring - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Learning',
    'summary': 'Standard Permission Management roles for SCORM Authoring',
    'description': """
        Installs automatically when both SCORM Authoring and Permission Management
        are installed, and adds these roles:

        - SCORM Authoring – Administrator: everything, including deleting any course,
          approving, publishing and Configuration
        - SCORM Authoring – Manager: create and edit their own and their team's courses
        - SCORM Authoring – Employee: create and edit their own courses
        - SCORM Authoring – Reviewer: view every course and add review comments
        - SCORM Authoring – Approver: view every course, comment, approve and publish
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['lms_scorm_authoring', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

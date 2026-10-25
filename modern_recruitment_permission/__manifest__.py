# -*- coding: utf-8 -*-
{
    'name': 'Talent - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Standard Permission Management roles for Talent',
    'description': """
        Installs automatically when both Talent and Permission Management are
        installed, and adds these roles (built on Recruitment's own access
        levels, which Odoo's Recruitment code depends on):

        - Talent – Administrator: everything, including Configuration, deleting
          applications and (with Checklists) sending questionnaires
        - Talent – Manager: manage every job position and application
          (Recruitment Officer)
        - Talent – Employee: the applications and job positions they interview
          for (Recruitment Interviewer)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

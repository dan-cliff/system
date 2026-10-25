# -*- coding: utf-8 -*-
{
    'name': 'Talent',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'A modern look for Recruitment, renamed Talent, with optional LinkedIn, SEEK and Jora job boards',
    'description': """
        Talent

        Restyles Odoo's Recruitment app and renames it Talent:

        - Applicant cards with a coloured avatar, the applied date and soft, rounded cards
        - Job Position cards and the applicant form restyled to match
        - Every list starts with the record ID; dates show as dd/mm/yyyy
        - A Reports menu for Report Builder, before Configuration
        - Configuration › Canned Responses: the canned responses kept for Talent

        Settings › Talent › Job Boards installs the job board apps:

        - LinkedIn (modern_recruitment_linkedin)
        - SEEK (modern_recruitment_seek)
        - Jora (modern_recruitment_jora)

        With Checklists installed, Talent can send pre-employment screening
        questionnaires to applicants (modern_recruitment_checklists, installed
        automatically).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['hr_recruitment', 'mail'],
    'data': [
        'data/res_lang_data.xml',
        'views/hr_applicant_views.xml',
        'views/hr_job_views.xml',
        'views/config_list_views.xml',
        'views/mail_canned_response_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'modern_recruitment/static/src/scss/talent.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}

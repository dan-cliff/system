# -*- coding: utf-8 -*-
{
    'name': 'Talent - Checklists',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Send pre-employment screening questionnaires (Checklists) to applicants',
    'description': """
        Installs automatically when both Talent and Checklists are installed.

        Settings › Talent › Checklists:

        - Integrate Checklists with Talent
        - Checklist Groups: the groups whose templates Talent can send

        Then:

        - Build screening questionnaires as Checklist Templates in those groups
        - Send Questionnaire (in the applicant's chatter) emails the applicant a
          link to fill the questionnaire in online, no login needed
        - When the applicant submits it, the checklist is completed and linked
          to the applicant and to the job position they applied for; the
          recruiter is notified
        - Applicants and job positions show their questionnaires
        - Talent canned responses can carry checklist templates, sent with
          them from Send Questionnaire

        Sending and viewing questionnaires takes the "Talent: Questionnaires"
        permission (Talent Administrators have it).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'checklists'],
    'data': [
        'security/talent_checklist_security.xml',
        'security/ir.model.access.csv',
        'security/talent_checklist_rules.xml',
        'data/talent_questionnaire_templates.xml',
        'wizard/talent_questionnaire_send_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_applicant_views.xml',
        'views/hr_job_views.xml',
        'views/checklist_views.xml',
        'views/mail_canned_response_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'modern_recruitment_checklists/static/src/chatter/*',
        ],
        'web.assets_frontend': [
            'checklists/static/src/checklist_checks/conditions.js',
            'modern_recruitment_checklists/static/src/questionnaire/*',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

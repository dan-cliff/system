# -*- coding: utf-8 -*-
{
    'name': 'Talent - Interview Forms',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Talent, not Recruitment, in the interview forms (surveys)',
    'description': """
        Installs automatically when both Talent and Recruitment's interview
        forms (hr_recruitment_survey) are installed, and calls Recruitment
        Talent there too: the survey type, the "Go to Talent" link and the
        app's name in the Apps list.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'hr_recruitment_survey'],
    'data': [
        'views/survey_templates.xml',
        'data/talent_titles.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

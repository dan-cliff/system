# -*- coding: utf-8 -*-
{
    'name': 'Talent - Online Jobs',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Talent, not Recruitment, in Online Jobs',
    'description': """
        Installs automatically when both Talent and Online Jobs
        (website_hr_recruitment) are installed, and calls Recruitment Talent
        there too: the job application thank-you page and the website form
        action.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'website_hr_recruitment'],
    'data': [
        'data/talent_titles.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

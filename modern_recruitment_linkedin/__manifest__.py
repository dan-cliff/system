# -*- coding: utf-8 -*-
{
    'name': 'Talent - LinkedIn',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'List Talent job positions on LinkedIn',
    'description': """
        Installed from Settings › Talent › Job Boards › LinkedIn.

        - A LinkedIn job feed (LinkedIn's XML job listings format) of the job
          positions ticked "List on LinkedIn" and published on the website.
          Give its address to LinkedIn (Talent Solutions / job wrapping) and
          LinkedIn reads it to keep the listings up to date.
        - Share on LinkedIn: posts the job page from the job position.
        - LinkedIn Job Type on each Employment Type, Workplace Type and
          Experience Level on each job position.
        - Applications made from the LinkedIn listing get LinkedIn as their Source.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'website_hr_recruitment'],
    'data': [
        'views/hr_contract_type_views.xml',
        'views/hr_job_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

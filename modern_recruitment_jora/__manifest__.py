# -*- coding: utf-8 -*-
{
    'name': 'Talent - Jora',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'List Talent job positions on Jora',
    'description': """
        Installed from Settings › Talent › Job Boards › Jora.

        - A Jora job feed (Jora's XML format) of the job positions ticked
          "List on Jora" and published on the website. Register its address
          with Jora (jora.com, Post jobs › XML feed) and Jora reads it to keep
          the listings up to date.
        - Jora Job Type on each Employment Type; salary text on each job.
        - Applications made from the Jora listing get Jora as their Source.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment', 'website_hr_recruitment'],
    'data': [
        'data/utm_source_data.xml',
        'views/hr_contract_type_views.xml',
        'views/hr_job_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

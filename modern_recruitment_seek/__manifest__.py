# -*- coding: utf-8 -*-
{
    'name': 'Talent - SEEK',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Post Talent job ads to SEEK and receive SEEK applications as applicants',
    'description': """
        Installed from Settings › Talent › Job Boards › SEEK.

        Uses the SEEK API (SEEK integration partner credentials, set in
        Settings › Talent › Job Boards):

        - Each job position has a SEEK tab: category, location, work type, pay
          and ad product, with Post to SEEK, Update and Close buttons
        - SEEK Categories and Locations come from SEEK (Configuration › SEEK);
          locations are looked up from SEEK as you type
        - SEEK Work Type on each Employment Type
        - Applications made on SEEK arrive through SEEK's webhook and become
          applicants on the job position (Source: SEEK), with their résumé and
          cover letter attached
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_recruitment'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/utm_source_data.xml',
        'views/talent_seek_option_views.xml',
        'views/hr_contract_type_views.xml',
        'views/hr_job_views.xml',
        'views/hr_applicant_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

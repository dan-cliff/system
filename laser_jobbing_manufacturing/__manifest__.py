# -*- coding: utf-8 -*-
{
    'name': 'Laser Jobbing - Manufacturing',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Collect and work through laser jobs in Manufacturing, with their files on '
               'manufacturing orders and in the Work Centre app',
    'description': """
        Installs automatically with Laser Jobbing and Manufacturing
        (advanced_manufacturing). Laser Jobbing has no menu of its own: this is
        where its jobs are collected and actioned.

        - Manufacturing › Operations › Laser Jobs: every job to make, by status.
        - Manufacturing › Configuration › Laser Templates, Laser Fonts and Laser
          Materials.
        - Manufacturing orders find the laser jobs of the order they are made
          for (same source document and product); confirming a job whose
          product has a bill of materials and no manufacturing order yet
          creates and confirms one (Settings › Laser Jobbing › Manufacturing
          Orders for Laser Jobs), or use Create Manufacturing Order on the job.
        - Manufacturing orders show their laser jobs (smart button and a Laser
          Files tab to download each file); starting a work order starts its
          jobs, producing the order marks them done.
        - Work Centre app: each work order lists its laser files with a preview
          and a download link, served through the work centre's own link.
    """,
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['laser_jobbing', 'advanced_manufacturing'],
    'data': [
        'views/laser_job_views.xml',
        'views/mrp_production_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'auto_install': True,
    'installable': True,
}

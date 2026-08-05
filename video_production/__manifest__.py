# -*- coding: utf-8 -*-
{
    'name': 'Video Production',
    'version': '19.0.1.0.0',
    'summary': 'End-to-end YouTube video production management',
    'description': """
Video Production Management
============================
Manage the full lifecycle of YouTube video production:

* Content ideation and planning pipeline
* Script and outline management with version history
* Production scheduling and publishing calendars
* Shoot management (crew, equipment, call sheets)
* Editing job tracking with version deliverables
* Collaboration and multi-stage review with approvals
* Thumbnail and YouTube metadata management
* Integration with Projects, Timesheets, CRM, Sales, Expenses,
  Asset Management, and Social Marketing
    """,
    'category': 'Marketing/Video Production',
    'author': 'Cliff\'s Country Crafts',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale',
        'purchase',
        'iot',
    ],
    'data': [
        # Security (load first)
        'security/video_production_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/video_production_data.xml',
        # Views
        'views/video_idea_stage_views.xml',
        'views/video_idea_ai_wizard_views.xml',
        'views/video_idea_views.xml',
        'views/video_production_stage_views.xml',
        'views/video_production_views.xml',
        'views/video_script_views.xml',
        'views/teleprompter_send_wizard_views.xml',
        'views/video_shoot_views.xml',
        'views/video_edit_job_views.xml',
        'views/video_review_views.xml',
        'views/video_metadata_views.xml',
        'views/video_metadata_seo_wizard_views.xml',
        'views/video_platform_views.xml',
        'views/res_config_settings_views.xml',
        'views/purchase_order_views.xml',
        'views/video_production_menus.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            'video_production/static/src/js/video_idea_ai_wizard.js',
            'video_production/static/src/xml/video_idea_ai_wizard.xml',
            'video_production/static/src/js/video_metadata_ai.js',
            'video_production/static/src/xml/video_metadata_ai.xml',
            'video_production/static/src/js/video_script_ai.js',
            'video_production/static/src/xml/video_script_ai.xml',
            'video_production/static/src/scss/video_idea_ai_wizard.scss',
        ],
    },
}

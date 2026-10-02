# -*- coding: utf-8 -*-
{
    'name': 'Incident Management',
    'version': '19.0.1.2.0',
    'category': 'Human Resources/Health & Safety',
    'summary': 'Workplace incident reporting, investigation (ICAM) and corrective action tracking',
    'description': """
        Workplace incident reporting and management system with:
        - Nine incident types: Injury, Illness, Vehicle, Plant & Equipment,
          Drug & Alcohol, Buildings & Grounds, Security, Theft, Environmental
        - Type-specific detail capture per incident
        - Guided workflow from reporting through to closure
        - Responsible Manager assignment
        - Configurable ICAM investigation methodology
        - Corrective action tracking with responsible parties
        - Full audit trail and chatter messaging
    """,
    'author': 'Custom',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/access_levels.xml',
        'security/incident_security.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/incident_sequence.xml',
        'data/incident_type_data.xml',
        'data/icam_data.xml',
        'wizards/incident_assign_wizard_views.xml',
        'views/icam_config_views.xml',
        'views/incident_corrective_action_views.xml',
        'views/incident_report_views.xml',
        'views/incident_analysis_views.xml',
        'views/incident_ai_settings_views.xml',
        'views/incident_confidential_wizard_views.xml',
        'views/incident_report_wizard_views.xml',
        'report/incident_case_report.xml',
        'views/res_config_settings_views.xml',
        'views/incident_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'incident_management/static/src/js/body_part_widget.js',
            'incident_management/static/src/xml/body_part_widget.xml',
            'incident_management/static/src/js/incident_ai_reload.js',
            'incident_management/static/src/xml/incident_ai_reload.xml',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}

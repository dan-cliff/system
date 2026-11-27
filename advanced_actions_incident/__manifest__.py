{
    'name': 'Incidents - Actions',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Health & Safety',
    'summary': "Keep Incidents' corrective actions in the Actions app",
    'description': """
        Installs automatically when both Incidents and Actions are installed.

        - Corrective actions are stored as Actions (one table for every app's
          actions); existing corrective actions, with their chatter, are moved
          there on install, and moved back if this module is uninstalled
        - Incidents › Management › Corrective Actions opens Actions filtered to
          Incidents (remove the filter to see every action)
        - Control Types (Hierarchy of Controls) become a list under Incidents ›
          Configuration
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['incident_management', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_incident_security.xml',
        'data/incident_control_type_data.xml',
        'views/incident_control_type_views.xml',
        'views/advanced_action_views.xml',
        'views/incident_report_views.xml',
        'report/incident_case_report.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

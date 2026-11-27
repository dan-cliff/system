{
    'name': 'Risk Management - Actions',
    'version': '19.0.1.0.0',
    'category': 'Operations/Risk Management',
    'summary': "Keep Risk Assessments' actions in the Actions app",
    'description': """
        Installs automatically when both Risk Management and Actions are installed.

        - The actions on a Risk Assessment's risks are stored as Actions (one
          table for every app's actions); existing ones are moved there on
          install, and moved back if this module is uninstalled
        - Risk Management › Actions opens Actions filtered to Risk Management
          (remove the filter to see every action)
        - Risk Templates' Standard Actions stay part of the template
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['risk_management', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_risk_security.xml',
        'views/advanced_action_views.xml',
        'views/risk_assessment_views.xml',
        'report/risk_assessment_report_templates.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

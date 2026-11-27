{
    'name': 'Feature Suggestions - Helpdesk',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Turn Helpdesk tickets into feature suggestions, or votes on existing ones',
    'description': """
        Installs automatically when both Feature Suggestions and Helpdesk are installed.

        - "Create Feature Suggestion" on a Helpdesk ticket posts a new suggestion from it, or
          adds the customer's vote (with how important it is and why) to an existing one
        - Helpdesk tickets and suggestions show each other
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['dev_feature_suggestions', 'helpdesk_management'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/dev_suggestion_from_helpdesk_views.xml',
        'views/helpdesk_ticket_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

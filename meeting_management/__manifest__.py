{
    'name': 'Meeting Management',
    'version': '19.0.1.1.0',
    'summary': 'Comprehensive meeting management with agenda, minutes, Teams integration and To-Do',
    'description': """
Meeting Management
==================
A full-featured meeting management solution for Odoo 19.0:

- Meeting records with invitees, agenda items and minutes
- Meeting template library with auto-scheduling
- Action items linked to the Odoo To-Do app
- Microsoft Teams / Outlook calendar integration (Graph API)
- Custom notification templates with field placeholders and PDF attachments
- PDF reports: Meeting Agenda and Meeting Minutes
- Settings menu for Teams/Outlook OAuth credentials and notification defaults
    """,
    'author': "Cliff's Country Crafts",
    'category': 'Productivity',
    'depends': [
        'base',
        'mail',
        'project',
    ],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/meeting_sequence.xml',
        'views/meeting_notification_template_views.xml',
        'views/meeting_template_views.xml',
        'views/meeting_meeting_views.xml',
        'views/meeting_send_notification_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
        'report/meeting_agenda_report.xml',
        'report/meeting_minutes_report.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'icon': 'static/description/icon.png',
}

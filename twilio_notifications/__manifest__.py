{
    'name': 'Twilio Notifications',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Route all outgoing email notifications through the Twilio Email API',
    'description': """
Twilio Notifications
=====================
Adds an "Enable Twilio Emails" toggle to Settings > General Settings >
Emails. When enabled, every outgoing email notification from Odoo is sent
through the Twilio Email API (https://comms.twilio.com/v1/Emails) using the
Twilio SID / Secret, From Email and From Name configured on the settings
page, instead of the usual SMTP mail servers.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

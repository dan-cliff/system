{
    'name': 'Emergency Broadcast',
    'version': '19.0.1.1.0',
    'category': 'Communication',
    'summary': 'Emergency broadcast messages with real-time notifications and acknowledgement tracking',
    'description': """
Emergency Broadcast
===================
Create and send emergency broadcast messages via multiple channels:
- Email
- SMS
- Popup Notification (real-time toast on logged-in workstations)
- Dialogue Box (modal requiring user acknowledgement, with tracking)

Features:
- Recipient filtering by Company, specific Users, or Logged-In status
- Real-time delivery via Odoo bus (WebSocket)
- Acknowledgement tracking with timestamps
- Status-based banners on all internal Odoo pages
- Emergency Assistance systray button
- Configurable settings for the assistance button
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'mail', 'sms', 'bus', 'web', 'web_enterprise', 'incident_management'],
    'data': [
        'security/access_levels.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/res_lang_data.xml',
        'data/emergency_broadcast_channel_data.xml',
        'data/emergency_broadcast_status_data.xml',
        'views/emergency_broadcast_status_views.xml',
        'views/emergency_broadcast_channel_views.xml',
        'views/emergency_broadcast_statusbar_config_views.xml',
        'views/emergency_broadcast_views.xml',
        'views/incident_report_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'emergency_broadcast/static/src/css/emergency_broadcast.css',
            'emergency_broadcast/static/src/js/emergency_broadcast_service.js',
            'emergency_broadcast/static/src/js/emergency_assistance_button.js',
            'emergency_broadcast/static/src/js/emergency_status_banner.js',
            'emergency_broadcast/static/src/xml/emergency_broadcast_dialog.xml',
            'emergency_broadcast/static/src/xml/emergency_assistance_button.xml',
            'emergency_broadcast/static/src/xml/emergency_status_banner.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'sequence': 100,
}

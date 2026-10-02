"""Emergency Broadcast access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py emergency_broadcast
"""

APP_NAME = 'Emergency Broadcast'
PREFIX = 'eb'
CATEGORY = 'module_category_emergency_broadcast'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('broadcast', 'Emergency Broadcasts', OPERATIONAL, {
        'model_emergency_broadcast': [],
        'model_emergency_broadcast_recipient': ['broadcast_id.create_uid', 'user_id'],
    }, []),
    ('status', 'Broadcast Statuses', CONFIG, ['model_emergency_broadcast_status'], []),
    ('channel', 'Delivery Channels', CONFIG, ['model_emergency_broadcast_channel'], []),
    ('statusbar_config', 'Statusbar Banners', CONFIG, ['model_emergency_broadcast_statusbar_config'], []),
    ('user_presence', 'User Presence', SETTINGS, ['model_emergency_broadcast_user_presence'], ['user_id']),
]

# Every internal user acknowledges the broadcasts sent to them and reports their presence.
EXTRA_ACCESS = [
    ('access_eb_recipient_internal', 'model_emergency_broadcast_recipient', 'base.group_user', 'rw'),
    ('access_eb_presence_internal', 'model_emergency_broadcast_user_presence', 'base.group_user', 'rwc'),
]

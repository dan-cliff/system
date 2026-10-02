"""Meeting Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py meeting_management
"""

APP_NAME = 'Meeting Management'
PREFIX = 'meeting'
CATEGORY = 'module_category_meeting_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# A user's own meetings: those they created, chair, take minutes for or are invited to.
_MEETING_OWNERS = ['chairperson_id.user_ids', 'secretary_id.user_ids', 'invitee_ids.user_ids']
_ON_MEETING = ['meeting_id.%s' % field for field in ['create_uid'] + _MEETING_OWNERS]

MODELS = [
    ('meeting', 'Meetings', OPERATIONAL, {
        'model_meeting_meeting': _MEETING_OWNERS,
        'model_meeting_agenda_item': ['presenter_id.user_ids'] + _ON_MEETING,
        'model_meeting_minutes_item': _ON_MEETING,
    }, []),
    ('action_item', 'Meeting Action Items', OPERATIONAL, ['model_meeting_action_item'],
     ['assigned_to_id.user_ids'] + _ON_MEETING),
    ('template', 'Meeting Templates', CONFIG,
     ['model_meeting_template', 'model_meeting_template_agenda_item'], []),
    ('notification_template', 'Notification Templates', CONFIG, ['model_meeting_notification_template'], []),
]

EXTRA_ACCESS = [
    ('access_meeting_send_notification_wizard', 'model_meeting_send_notification_wizard',
     'group_meeting_meeting_view', 'rwcu'),
]

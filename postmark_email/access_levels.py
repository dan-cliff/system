"""Postmark Email access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py postmark_email
"""

APP_NAME = 'Postmark Email'
PREFIX = 'postmark'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('email_log', 'Postmark Email Logs', SETTINGS, ['model_postmark_email_log'], []),
    ('message_stream', 'Postmark Message Streams', SETTINGS, ['model_postmark_message_stream'], []),
    ('reply_rule', 'Postmark Reply Rules', SETTINGS, ['model_postmark_reply_rule'], []),
]

# Settings administrators keep full access and internal users read streams and reply
# rules (used when sending mail), as before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_postmark_message_stream_user', 'model_postmark_message_stream', 'base.group_user', 'r'),
    ('access_postmark_message_stream_admin', 'model_postmark_message_stream', 'base.group_system', 'rwcu'),
    ('access_postmark_reply_rule_user', 'model_postmark_reply_rule', 'base.group_user', 'r'),
    ('access_postmark_reply_rule_admin', 'model_postmark_reply_rule', 'base.group_system', 'rwcu'),
    ('access_postmark_email_log_admin', 'model_postmark_email_log', 'base.group_system', 'rwcu'),
]

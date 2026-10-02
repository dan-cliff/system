"""Mandrill Mail access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py mandrill_mail
"""

APP_NAME = 'Mandrill Mail'
PREFIX = 'mandrill'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('mail_log', 'Mandrill Mail Logs', SETTINGS, ['model_mandrill_mail_log'], []),
    ('reply_route', 'Mandrill Reply Routes', SETTINGS, ['model_mandrill_reply_route'], []),
]

# Settings administrators keep full access and internal users read reply routes (used when
# sending mail), as before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_mandrill_mail_log_system', 'model_mandrill_mail_log', 'base.group_system', 'rwcu'),
    ('access_mandrill_reply_route_system', 'model_mandrill_reply_route', 'base.group_system', 'rwcu'),
    ('access_mandrill_reply_route_user', 'model_mandrill_reply_route', 'base.group_user', 'r'),
]

"""Membership access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py membership_management
"""

APP_NAME = 'Memberships'
PREFIX = 'membership'
CATEGORY = 'base.module_category_sales'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('membership', 'Memberships', OPERATIONAL, ['model_membership_membership'], ['partner_id.user_ids']),
    ('status', 'Membership Statuses', CONFIG, ['model_membership_status'], []),
    ('letter_template', 'Membership Letter Templates', CONFIG, ['model_membership_letter_template'], []),
    ('email_template', 'Membership Email Templates', CONFIG, ['model_membership_email_template'], []),
]

EXTRA_ACCESS = [
    ('access_membership_email_field_browser', 'model_membership_email_field_browser',
     'group_membership_email_template_view', 'rwcu'),
    ('access_membership_letter_wizard', 'model_membership_letter_wizard', 'group_membership_membership_view', 'rwcu'),
    ('access_membership_email_wizard', 'model_membership_email_wizard', 'group_membership_membership_view', 'rwcu'),
]

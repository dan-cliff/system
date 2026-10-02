"""Login As Any User access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py login_as_any_user
"""

APP_NAME = 'Login As Any User'
PREFIX = 'login_as'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('user_selection', 'Login As Selections', SETTINGS, ['model_user_selection'], []),
]

# Which users may log in as another user is decided by their groups (see res_groups.py);
# the selection records themselves stay open to internal users, as before.
EXTRA_ACCESS = [
    ('access_user_selection_user', 'model_user_selection', 'base.group_user', 'rwcu'),
]

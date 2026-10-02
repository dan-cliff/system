"""Home Screen access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py web_home_menu
"""

APP_NAME = 'Home Screen'
PREFIX = 'home_menu'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# Folders and quick launch buttons are managed from the Settings app, so they are SETTINGS.
MODELS = [
    ('folder', 'Home Screen Folders', SETTINGS,
     {'model_home_menu_folder': ['user_id'], 'model_home_menu_folder_app': ['folder_id.user_id']}, []),
    ('quick_link', 'Home Screen Quick Launch', SETTINGS, ['model_home_menu_quick_link'], ['user_id']),
]

# Every internal user reads the default layout and keeps their own (see the record rules
# in home_menu_security.xml), as before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_home_menu_folder_user', 'model_home_menu_folder', 'base.group_user', 'rwcu'),
    ('access_home_menu_folder_app_user', 'model_home_menu_folder_app', 'base.group_user', 'rwcu'),
    ('access_home_menu_quick_link_user', 'model_home_menu_quick_link', 'base.group_user', 'rwcu'),
]

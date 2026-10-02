"""Home Launcher access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py home_launcher
"""

APP_NAME = 'Home Launcher'
PREFIX = 'home'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# The Home Layout is managed from the Settings app, so it is SETTINGS.
MODELS = [
    ('toolbox', 'Home Layouts', SETTINGS, ['model_home_toolbox', 'model_home_toolbox_app'], ['user_id']),
]

# Every internal user reads the shared layout and keeps their own override (see the
# record rules in home_launcher_security.xml), as before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_home_toolbox_user', 'model_home_toolbox', 'base.group_user', 'rwcu'),
    ('access_home_toolbox_app_user', 'model_home_toolbox_app', 'base.group_user', 'rwcu'),
]

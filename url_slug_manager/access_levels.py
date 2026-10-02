"""URL Slug Manager access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py url_slug_manager
"""

APP_NAME = 'URL Slug Manager'
PREFIX = 'url_slug'
CATEGORY = 'module_category_technical_configuration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('config', 'URL Slugs', SETTINGS, ['model_url_slug_config'], []),
]

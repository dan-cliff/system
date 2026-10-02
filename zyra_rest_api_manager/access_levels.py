"""REST API Manager access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py zyra_rest_api_manager
"""

APP_NAME = 'REST API Manager'
PREFIX = 'api'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# All under Settings > API Management, so SETTINGS.
MODELS = [
    ('app_key', 'API App Keys', SETTINGS, ['model_api_app_key'], []),
    ('auth_endpoint', 'API Auth Endpoints', SETTINGS, ['model_api_auth_endpoint'], []),
    ('model_endpoint', 'API Model Endpoints', SETTINGS,
     ['model_api_model_endpoint', 'model_api_model_endpoint_relation'], []),
    ('custom_endpoint', 'API Custom Endpoints', SETTINGS, ['model_api_custom_endpoint'], []),
    ('rate_limit_log', 'API Rate Limit Logs', SETTINGS, ['model_api_rate_limit_log'], []),
    ('auth_cooldown_log', 'API Auth Cooldown Logs', SETTINGS, ['model_api_auth_cooldown_log'], []),
]

# Settings administrators keep the access they had before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_api_app_key', 'model_api_app_key', 'base.group_system', 'rwcu'),
    ('access_api_auth_endpoint', 'model_api_auth_endpoint', 'base.group_system', 'rwcu'),
    ('access_api_model_endpoint', 'model_api_model_endpoint', 'base.group_system', 'rwcu'),
    ('access_api_custom_endpoint', 'model_api_custom_endpoint', 'base.group_system', 'rwcu'),
    ('access_api_rate_limit_log', 'model_api_rate_limit_log', 'base.group_system', 'r'),
    ('access_api_model_endpoint_relation', 'model_api_model_endpoint_relation', 'base.group_system', 'rwcu'),
    ('access_api_auth_cooldown_log', 'model_api_auth_cooldown_log', 'base.group_system', 'rwcu'),
]

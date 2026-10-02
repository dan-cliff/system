"""Permission Management access levels - see access_levels_lib.py in this module.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py permission_management
"""

APP_NAME = 'Permission Management'
PREFIX = 'permission'
CATEGORY = 'module_category_permission_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# Roles and profiles live under Settings > Users & Companies, so they are SETTINGS.
MODELS = [
    ('role', 'Roles', SETTINGS, ['model_permission_role', 'model_permission_role_line'], []),
    ('profile', 'Profiles', SETTINGS, ['model_permission_profile'], []),
]

# Assigning roles changes users' groups, which needs Odoo's Access Rights administrator.
ROLE_EXTRA_GROUPS = {
    'Administrator': ['base.group_erp_manager'],
}

# Internal users read roles and profiles (shown on their user record); Access Rights
# administrators keep full access, as before this module moved to access levels.
EXTRA_ACCESS = [
    ('access_%s_%s' % (xmlid[len('model_'):], suffix), xmlid, group, perms)
    for xmlid in ('model_permission_role', 'model_permission_role_line', 'model_permission_profile')
    for suffix, group, perms in (('internal', 'base.group_user', 'r'), ('erp_manager', 'base.group_erp_manager', 'rwcu'))
]

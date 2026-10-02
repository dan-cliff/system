"""Asset Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py asset_management
"""

APP_NAME = 'Asset Management'
PREFIX = 'asset'
CATEGORY = 'module_category_asset_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_ASSET_OWNER = ['asset_id.assigned_to_id.user_id']

MODELS = [
    ('asset', 'Assets', OPERATIONAL, ['model_asset_asset'], ['assigned_to_id.user_id']),
    ('usage_log', 'Usage Logs', OPERATIONAL, ['model_asset_usage_log'], ['user_id'] + _ASSET_OWNER),
    ('defect', 'Defects', OPERATIONAL, ['model_asset_defect'], ['reported_by'] + _ASSET_OWNER),
    ('maintenance_log', 'Maintenance Logs', OPERATIONAL, ['model_asset_maintenance_log'],
     ['performed_by'] + _ASSET_OWNER),
    ('location_log', 'Location Logs', OPERATIONAL, ['model_asset_location_log'], _ASSET_OWNER),
    ('type', 'Asset Types', CONFIG, ['model_asset_type'], []),
    ('subtype', 'Asset Sub-Types', CONFIG, ['model_asset_subtype'], []),
    ('usage_unit', 'Usage Units', CONFIG, ['model_asset_usage_unit'], []),
    ('maintenance_type', 'Maintenance Types', CONFIG, ['model_asset_maintenance_type'], []),
    ('defect_severity', 'Defect Severities', CONFIG, ['model_asset_defect_severity'], []),
]

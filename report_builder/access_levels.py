"""Report Builder access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py report_builder
"""

APP_NAME = 'Report Builder'
PREFIX = 'report_builder'
CATEGORY = 'base.module_category_technical'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('report', 'Reports', OPERATIONAL, {
        'model_report_builder': [],
        'model_report_builder_column': ['report_id.create_uid'],
    }, []),
]

_FULL = ('view', 'create', 'update', 'delete')

ROLES = {
    'Administrator': ('Designs and manages every report.', {'report': _FULL}),
    'Manager': ('Designs and manages every report.', {'report': _FULL}),
    'Employee': ('Runs the reports others have designed.', {'report': ('view',)}),
    'View Only': ('Runs the reports others have designed.', {'report': ('view',)}),
}

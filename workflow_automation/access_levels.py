"""Workflow Automation access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py workflow_automation

Workflows run code and call external services, and they appear in the Settings app, so
every model is SETTINGS: only the Administrator role manages them. Internal users keep
read access (EXTRA_ACCESS) because automations triggered by their own changes read the
workflow definitions as that user.
"""

APP_NAME = 'Workflow Automation'
PREFIX = 'wf'
CATEGORY = 'base.module_category_administration'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_STEP_MODELS = [
    'model_wf_step', 'model_wf_step_field_mapping', 'model_wf_step_connection',
    'model_wf_step_api_header', 'model_wf_step_api_body_param', 'model_wf_step_api_query_param',
]
_PLATFORM_MODELS = [
    'model_wf_service_platform', 'model_wf_service_platform_header', 'model_wf_service_platform_body_param',
]

MODELS = [
    ('automation', 'Workflows', SETTINGS, ['model_wf_automation'] + _STEP_MODELS, []),
    ('execution_log', 'Workflow Execution Logs', SETTINGS,
     ['model_wf_execution_log', 'model_wf_execution_log_step'], []),
    ('api_call_log', 'API Call Logs', SETTINGS, ['model_wf_api_call_log'], []),
    ('service_platform', 'Services / Platforms', SETTINGS, _PLATFORM_MODELS, []),
]

_READ_ALL = [
    'model_wf_automation', 'model_wf_step', 'model_wf_step_field_mapping', 'model_wf_step_connection',
    'model_wf_execution_log', 'model_wf_execution_log_step', 'model_wf_api_call_log',
] + _PLATFORM_MODELS
_EDIT_ALL = ['model_wf_step_api_header', 'model_wf_step_api_body_param', 'model_wf_step_api_query_param']

EXTRA_ACCESS = (
    [('access_%s_internal' % xmlid[len('model_'):], xmlid, 'base.group_user', 'r') for xmlid in _READ_ALL]
    + [('access_%s_internal' % xmlid[len('model_'):], xmlid, 'base.group_user', 'rwcu') for xmlid in _EDIT_ALL]
    + [('access_wf_manual_run_wizard', 'model_wf_manual_run_wizard', 'base.group_user', 'rwcu')]
    # Settings administrators keep full access, as before this module moved to access levels.
    + [('access_%s_system' % xmlid[len('model_'):], xmlid, 'base.group_system', 'rwcu')
       for xmlid in _READ_ALL + _EDIT_ALL]
)

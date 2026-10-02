"""Incident Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py incident_management
"""

APP_NAME = 'Incident Management'
PREFIX = 'incident'
CATEGORY = 'module_category_incident_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_REPORT_OWNERS = [
    'reporter_id', 'employee_id.user_id', 'responsible_manager_id', 'investigator_ids',
    'confidential_user_ids',
]

MODELS = [
    ('report', 'Incident Reports', OPERATIONAL, ['model_incident_report'], _REPORT_OWNERS),
    ('icam_finding', 'ICAM Findings', OPERATIONAL, ['model_incident_icam_finding'],
     ['incident_id.%s' % field for field in ['create_uid'] + _REPORT_OWNERS]),
    ('corrective_action', 'Corrective Actions', OPERATIONAL, ['model_incident_corrective_action'],
     ['responsible_id', 'verified_by_id', 'incident_id.reporter_id', 'incident_id.responsible_manager_id']),
    ('analysis', 'Incident Analysis', OPERATIONAL, ['model_incident_report_analysis'],
     ['-create_uid', 'incident_id.create_uid', 'incident_id.reporter_id', 'responsible_manager_id']),
    ('type_tag', 'Incident Categories', CONFIG, ['model_incident_type_tag'], []),
    ('icam_category', 'ICAM Categories', CONFIG, ['model_icam_category'], []),
    ('icam_factor', 'ICAM Factors', CONFIG, ['model_icam_factor'], []),
    ('ai_settings', 'AI Settings', SETTINGS, ['model_incident_ai_settings'], []),
]

ROLE_EXTRA_GROUPS = {
    'Administrator': ['incident_management.group_incident_confidential_bypass'],
}

EXTRA_ACCESS = [
    ('access_incident_assign_wizard', 'model_incident_assign_wizard', 'group_incident_report_update', 'rwcu'),
    ('access_incident_confidential_wizard', 'model_incident_confidential_wizard',
     'group_incident_report_update', 'rwcu'),
    ('access_incident_report_wizard', 'model_incident_report_wizard', 'group_incident_report_view', 'rwcu'),
]

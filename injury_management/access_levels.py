"""Injury Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py injury_management
"""

APP_NAME = 'Injury Management'
PREFIX = 'injury'
CATEGORY = 'module_category_injury_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_CASE_OWNERS = ['create_uid', 'case_manager_id', 'employee_id.user_id']
_ON_CASE = ['case_id.%s' % field for field in _CASE_OWNERS]

MODELS = [
    ('rtw_case', 'Return to Work Cases', OPERATIONAL, ['model_injury_rtw_case'], _CASE_OWNERS),
    ('case_note', 'Case Notes', OPERATIONAL, ['model_injury_case_note'], ['author_id'] + _ON_CASE),
    ('medical_appointment', 'Medical Appointments', OPERATIONAL, ['model_injury_medical_appointment'], _ON_CASE),
    ('meeting', 'RTW Meetings', OPERATIONAL, ['model_injury_meeting'], _ON_CASE),
    ('file_note', 'File Notes', OPERATIONAL, ['model_injury_file_note'], ['author_id'] + _ON_CASE),
    ('cost', 'Case Costs', OPERATIONAL, ['model_injury_cost'], _ON_CASE),
    ('rtw_plan', 'Return to Work Plans', OPERATIONAL, {
        'model_injury_rtw_plan': ['approved_by_id'] + _ON_CASE,
        'model_injury_rtw_plan_line': ['plan_id.%s' % field for field in _ON_CASE],
    }, []),
    ('medical_certificate', 'Medical Certificates', OPERATIONAL, ['model_injury_medical_certificate'], _ON_CASE),
    ('case_document', 'Case Documents', OPERATIONAL, ['model_injury_case_document'], ['-create_uid'] + _ON_CASE),
]

EXTRA_ACCESS = [
    ('access_injury_case_report_wizard', 'model_injury_case_report_wizard', 'group_injury_rtw_case_view', 'rwcu'),
]

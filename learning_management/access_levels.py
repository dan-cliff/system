"""Learning Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py learning_management
"""

APP_NAME = 'Learning Management'
PREFIX = 'lms'
CATEGORY = 'module_category_lms'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

# An employee's own training records, and those of the employees who report to them.
_EMPLOYEE_OWNERS = ['employee_id.user_id', 'employee_id.parent_id.user_id']

MODELS = [
    ('course', 'Courses', OPERATIONAL, ['model_lms_course'], []),
    ('course_group', 'Training Packages', OPERATIONAL, ['model_lms_course_group'], []),
    ('session', 'Course Sessions', OPERATIONAL, ['model_lms_course_session'], ['instructor_id.user_id']),
    ('enrollment', 'Session Enrolments', OPERATIONAL, ['model_lms_session_enrollment'], _EMPLOYEE_OWNERS),
    ('assignment', 'Training Package Assignments', OPERATIONAL, ['model_lms_course_group_assignment'],
     _EMPLOYEE_OWNERS),
    ('employee_record', 'Employee Training Records', OPERATIONAL, ['model_lms_employee_record'],
     ['verified_by'] + _EMPLOYEE_OWNERS),
    ('assessment_template', 'Assessment Templates', OPERATIONAL, [
        'model_lms_assessment_template', 'model_lms_assessment_question',
        'model_lms_assessment_question_option',
    ], []),
    ('assessment', 'Assessments', OPERATIONAL, {
        'model_lms_assessment': ['assessor_id'] + _EMPLOYEE_OWNERS,
        'model_lms_assessment_answer': ['assessment_id.assessor_id'] + [
            'assessment_id.%s' % field for field in _EMPLOYEE_OWNERS],
    }, []),
    ('course_category', 'Course Categories', CONFIG, ['model_lms_course_category'], []),
    ('notification_template', 'Notification Templates', SETTINGS, ['model_lms_notification_template'], []),
    ('notification_log', 'Notification History', SETTINGS, ['model_lms_notification_log'], []),
]

_FULL = ('view', 'create', 'update', 'delete')
_OPERATIONAL = [model[0] for model in MODELS if model[2] == OPERATIONAL]
_LIBRARY = ('course', 'course_group', 'session', 'assessment_template')

ROLES = {
    'Administrator': (
        'Full access to every Learning Management record, including Course Categories, '
        'Notification Templates and Notification History.',
        {model[0]: _FULL for model in MODELS},
    ),
    'Manager': (
        'Manages courses, training packages, sessions, enrolments, training records and '
        'assessments for everyone. No access to Configuration or Settings.',
        {key: _FULL for key in _OPERATIONAL},
    ),
    'Employee': (
        'Views the course library and sessions, and creates and edits their own (and their '
        "direct reports') enrolments, training records and assessments. Confirms their direct "
        "reports' enrolments. No access to Configuration or Settings.",
        dict({key: ('view',) for key in _LIBRARY},
             **{key: ('view', 'own') for key in _OPERATIONAL if key not in _LIBRARY}),
    ),
    'View Only': (
        'Views Learning Management records without changing them. No access to Configuration '
        'or Settings.',
        {key: ('view',) for key in _OPERATIONAL},
    ),
}

"""Risk Management access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py risk_management
"""

APP_NAME = 'Risk Management'
PREFIX = 'risk'
CATEGORY = 'module_category_risk_management'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_ASSESSMENT_OWNERS = ['assessor_id', 'approver_id', 'collaborator_ids']

MODELS = [
    ('assessment', 'Risk Assessments', OPERATIONAL, ['model_risk_assessment'], _ASSESSMENT_OWNERS),
    ('risk', 'Risks', OPERATIONAL, ['model_risk_assessment_line'],
     ['assessment_id.create_uid'] + ['assessment_id.%s' % field for field in _ASSESSMENT_OWNERS]),
    ('template', 'Risk Templates', CONFIG,
     ['model_risk_template', 'model_risk_template_line', 'model_risk_template_action'], []),
    ('category', 'Risk Categories', CONFIG, ['model_risk_category'], []),
    ('control', 'Controls', CONFIG, ['model_risk_control'], []),
    ('control_hierarchy', 'Hierarchy of Controls', CONFIG, ['model_risk_control_hierarchy'], []),
    ('type', 'Risk Types', CONFIG, ['model_risk_type'], []),
    ('subtype', 'Risk Subtypes', CONFIG, ['model_risk_subtype'], []),
    ('stage', 'Risk Assessment Stages', CONFIG, ['model_risk_assessment_stage'], []),
    ('likelihood', 'Likelihood', CONFIG, ['model_risk_likelihood'], []),
    ('consequence', 'Consequence', CONFIG, ['model_risk_consequence'], []),
    ('severity', 'Risk Severity', CONFIG, ['model_risk_severity'], []),
    ('score', 'Risk Score', CONFIG, ['model_risk_score'], []),
]

_FULL = ('view', 'create', 'update', 'delete')
_LIBRARY = ('template', 'category', 'control', 'type', 'subtype')

ROLES = {
    'Administrator': (
        'Full access to every Risk Management record, including Risk Templates and all '
        'Configuration lists.',
        {model[0]: _FULL for model in MODELS},
    ),
    'Risk Manager': (
        'Manages every Risk Assessment, the Risk Templates and the risk library (Categories, '
        'Types, Subtypes and Controls).',
        dict({'assessment': _FULL, 'risk': _FULL}, **{key: _FULL for key in _LIBRARY}),
    ),
    'Manager': (
        'Creates, updates, approves and archives every Risk Assessment and its Risks. No '
        'access to Configuration.',
        {'assessment': _FULL, 'risk': _FULL},
    ),
    'Employee': (
        'Creates and edits the Risk Assessments (and their Risks) they created or are the Risk '
        'Assessment Owner, Risk Approver or a Collaborator on. No access to Configuration.',
        {'assessment': ('view', 'own'), 'risk': ('view', 'own')},
    ),
    'View Only': (
        'Views Risk Assessments and their Risks without changing them. No access to '
        'Configuration.',
        {'assessment': ('view',), 'risk': ('view',)},
    ),
}

EXTRA_ACCESS = [
    ('access_risk_matrix_wizard_score_view', 'model_risk_matrix_wizard', 'group_risk_score_view', 'rwc'),
    ('access_risk_assessment_approval_wizard_update', 'model_risk_assessment_approval_wizard',
     'group_risk_assessment_update', 'rwcu'),
    ('access_risk_assessment_approval_wizard_own', 'model_risk_assessment_approval_wizard',
     'group_risk_assessment_own', 'rwc'),
]

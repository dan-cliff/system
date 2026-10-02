"""Risk Management access levels and the Permission Management roles built from them.

Each risk model has its own privilege (shown as "<model name>") holding four
groups: View Only, Create, Update and Delete, so they display as
"Risk Templates / Create", "Risk Templates / Delete" and so on. Create,
Update and Delete each imply View Only for the same model.
"""

# (key, privilege name) - XML IDs are privilege_risk_<key> and group_risk_<key>_<permission>.
RISK_MODELS = [
    ('assessment', 'Risk Assessments'),
    ('risk', 'Risks'),
    ('template', 'Risk Templates'),
    ('category', 'Risk Categories'),
    ('control', 'Controls'),
    ('control_hierarchy', 'Hierarchy of Controls'),
    ('type', 'Risk Types'),
    ('subtype', 'Risk Subtypes'),
    ('stage', 'Risk Assessment Stages'),
    ('likelihood', 'Likelihood'),
    ('consequence', 'Consequence'),
    ('severity', 'Risk Severity'),
    ('score', 'Risk Score'),
]

PERMISSIONS = ['view', 'create', 'update', 'delete']

ALL = ('view', 'create', 'update', 'delete')
VIEW = ('view',)

# Role name -> (description, {model key: permissions}); models not listed get View Only.
ROLES = {
    'Administrator': (
        'Full access to every Risk Management record, including Risk Templates and all '
        'Configuration lists.',
        {key: ALL for key, _name in RISK_MODELS},
    ),
    'Risk Manager': (
        'Manages Risk Assessments, Risk Templates and the risk library (Categories, Types, '
        'Subtypes and Controls). Views the Risk Matrix and Stage configuration.',
        {key: ALL for key in (
            'assessment', 'risk', 'template', 'category', 'control', 'type', 'subtype',
        )},
    ),
    'Manager': (
        'Creates, updates, approves and archives Risk Assessments and their Risks, and can add '
        'new Controls. Views Risk Templates and Configuration.',
        {'assessment': ALL, 'risk': ALL, 'control': ('view', 'create')},
    ),
    'Employee': (
        'Creates and updates Risk Assessments and their Risks, and can add new Controls. '
        'Views Risk Templates and Configuration.',
        {
            'assessment': ('view', 'create', 'update'),
            'risk': ALL,
            'control': ('view', 'create'),
        },
    ),
    'View Only': (
        'Views Risk Assessments, Risk Templates and Configuration without changing them.',
        {},
    ),
}

ROLE_NAME_PREFIX = 'Risk Management – '


def group_xmlid(key, permission):
    return 'risk_management.group_risk_%s_%s' % (key, permission)


def privilege_xmlid(key):
    return 'risk_management.privilege_risk_%s' % key


def role_access(role_name):
    """Return [(model key, permission), ...] for a role, defaulting unlisted models to View Only."""
    access = ROLES[role_name][1]
    return [
        (key, permission)
        for key, _name in RISK_MODELS
        for permission in access.get(key, VIEW)
    ]

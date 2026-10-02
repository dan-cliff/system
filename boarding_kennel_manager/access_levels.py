"""Boarding Kennel Manager access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py boarding_kennel_manager
"""

APP_NAME = 'Boarding Kennel Manager'
PREFIX = 'kennel'
CATEGORY = 'base.module_category_services'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

_ON_BOOKING = ['booking_id.user_id', 'booking_id.create_uid']

MODELS = [
    ('booking', 'Bookings', OPERATIONAL, {
        'model_kennel_booking': ['user_id'],
        'model_kennel_booking_line': _ON_BOOKING,
    }, []),
    ('resident', 'Residents', OPERATIONAL, ['model_kennel_resident'], []),
    ('task', 'Daily Tasks', OPERATIONAL, ['model_kennel_task'], ['done_by_id'] + _ON_BOOKING),
    ('medication', 'Medication', OPERATIONAL, {
        'model_kennel_medication': _ON_BOOKING,
        'model_kennel_medication_administration': ['user_id'] + _ON_BOOKING,
    }, []),
    ('observation', 'Observations', OPERATIONAL, ['model_kennel_observation'], ['user_id'] + _ON_BOOKING),
    ('yard', 'Yards', OPERATIONAL, ['model_kennel_yard'], []),
    ('diet', 'Diets', CONFIG, ['model_kennel_diet'], []),
    ('species', 'Species', CONFIG, ['model_kennel_species'], []),
    ('sex', 'Sexes', CONFIG, ['model_kennel_sex'], []),
    ('yard_type', 'Yard Types', CONFIG, ['model_kennel_yard_type'], []),
    ('yard_feature', 'Yard Features', CONFIG, ['model_kennel_yard_feature'], []),
    ('frequency', 'Frequencies', CONFIG, ['model_kennel_frequency'], []),
    ('feed_consumption', 'Food Eaten', CONFIG, ['model_kennel_feed_consumption'], []),
    ('medication_route', 'Medication Routes', CONFIG, ['model_kennel_medication_route'], []),
    ('dose_outcome', 'Dose Outcomes', CONFIG, ['model_kennel_dose_outcome'], []),
    ('observation_type', 'Observation Types', CONFIG, ['model_kennel_observation_type'], []),
]

_FULL = ('view', 'create', 'update', 'delete')
_OPERATIONAL = [model[0] for model in MODELS if model[2] == OPERATIONAL]

# Keepers care for every animal in the kennels, not only the bookings they made, so the
# Employee role works on all bookings and care records rather than Create and Edit Own Only.
ROLES = {
    'Administrator': (
        'Full access to every Boarding Kennel Manager record, including diets and all '
        'Configuration lists, and inviting customers to the portal.',
        {model[0]: _FULL for model in MODELS},
    ),
    'Manager': (
        'Manages every booking, resident, yard and care record, including deleting them. No '
        'access to Configuration.',
        {key: _FULL for key in _OPERATIONAL},
    ),
    'Employee': (
        'Keeper: works the daily to-do list and manages bookings, residents, medication and '
        'observations. Views yards. Cannot delete bookings or residents. No access to '
        'Configuration.',
        {
            'booking': ('view', 'create', 'update'),
            'resident': ('view', 'create', 'update'),
            'task': ('view', 'create', 'update'),
            'medication': _FULL,
            'observation': ('view', 'create', 'update'),
            'yard': ('view',),
        },
    ),
    'View Only': (
        'Views bookings, residents, yards and care records without changing them. No access '
        'to Configuration.',
        {key: ('view',) for key in _OPERATIONAL},
    ),
}

ROLE_EXTRA_GROUPS = {
    'Administrator': ['boarding_kennel_manager.group_kennel_portal_user'],
}

EXTRA_ACCESS = [
    ('access_kennel_custom_diet_wizard', 'model_kennel_custom_diet_wizard', 'group_kennel_booking_update', 'rwcu'),
    ('access_kennel_resident_portal', 'model_kennel_resident', 'base.group_portal', 'r'),
    ('access_kennel_booking_portal', 'model_kennel_booking', 'base.group_portal', 'r'),
    ('access_portal_wizard_kennel_portal_user', 'portal.model_portal_wizard', 'group_kennel_portal_user', 'rwc'),
    ('access_portal_wizard_user_kennel_portal_user', 'portal.model_portal_wizard_user',
     'group_kennel_portal_user', 'rwc'),
]

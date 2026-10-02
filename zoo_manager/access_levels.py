"""Zoo Manager access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py zoo_manager
"""

APP_NAME = 'Zoo Manager'
PREFIX = 'zoo'
CATEGORY = 'base.module_category_services'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('animal', 'Animals', OPERATIONAL, {
        'model_zoo_animal': [],
        'model_zoo_animal_note': ['user_id', 'animal_id.create_uid'],
    }, []),
    ('animal_move', 'Animal Moves', OPERATIONAL, ['model_zoo_animal_move'], ['user_id']),
    ('animal_weight', 'Animal Weights', OPERATIONAL, ['model_zoo_animal_weight'], ['user_id']),
    ('feeding', 'Feeding Rounds', OPERATIONAL, {
        'model_zoo_feeding': ['user_id'],
        'model_zoo_feeding_line': ['feeding_id.user_id', 'feeding_id.create_uid'],
    }, []),
    ('health_record', 'Health Records', OPERATIONAL, ['model_zoo_health_record'], ['user_id']),
    ('enclosure', 'Enclosures', OPERATIONAL, ['model_zoo_enclosure'], []),
    ('animal_class', 'Animal Classes', CONFIG, ['model_zoo_animal_class'], []),
    ('species', 'Species', CONFIG, ['model_zoo_species'], []),
    ('diet', 'Diets', CONFIG, ['model_zoo_diet', 'model_zoo_diet_line'], []),
    ('facility', 'Facilities', CONFIG, ['model_zoo_facility'], []),
    ('location', 'Locations', CONFIG, ['model_zoo_location'], []),
    ('enclosure_type', 'Enclosure Types', CONFIG, ['model_zoo_enclosure_type'], []),
    ('climate_control_type', 'Types of Climate Control', CONFIG, ['model_zoo_climate_control_type'], []),
    ('water_source_type', 'Types of Water Sources', CONFIG, ['model_zoo_water_source_type'], []),
    ('animal_origin', 'Animal Origins', CONFIG, ['model_zoo_animal_origin'], []),
    ('conservation_status', 'Conservation Statuses', CONFIG, ['model_zoo_conservation_status'], []),
    ('health_record_type', 'Health Record Types', CONFIG, ['model_zoo_health_record_type'], []),
    ('diet_frequency', 'Diet Frequencies', CONFIG, ['model_zoo_diet_frequency'], []),
    ('feeding_consumption', 'Food Consumption', CONFIG, ['model_zoo_feeding_consumption'], []),
]

_FULL = ('view', 'create', 'update', 'delete')
_OPERATIONAL = [model[0] for model in MODELS if model[2] == OPERATIONAL]

# Keepers look after every animal, not only the ones they registered, so the Employee
# role works on all animals and care records rather than Create and Edit Own Only.
ROLES = {
    'Administrator': (
        'Full access to every Zoo Manager record, including species, diets, facilities and '
        'all Configuration lists.',
        {model[0]: _FULL for model in MODELS},
    ),
    'Manager': (
        'Manages every animal, enclosure and care record, including deleting them. No access '
        'to Configuration.',
        {key: _FULL for key in _OPERATIONAL},
    ),
    'Employee': (
        'Keeper: registers and moves animals, and logs feedings, weights, health records and '
        'notes. Views enclosures. Cannot delete records. No access to Configuration.',
        {
            'animal': ('view', 'create', 'update'),
            'animal_move': ('view', 'create'),
            'animal_weight': _FULL,
            'feeding': ('view', 'create', 'update'),
            'health_record': ('view', 'create', 'update'),
            'enclosure': ('view',),
        },
    ),
    'View Only': (
        'Views animals, enclosures and care records without changing them. No access to '
        'Configuration.',
        {key: ('view',) for key in _OPERATIONAL},
    ),
}

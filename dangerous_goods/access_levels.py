"""Dangerous Goods access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py dangerous_goods
"""

APP_NAME = 'Dangerous Goods'
PREFIX = 'dg'
CATEGORY = 'module_category_dangerous_goods'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('chemical', 'Chemical Register', OPERATIONAL, ['model_dg_chemical'],
     ['responsible_person_id', 'chemical_owner_id.user_id']),
    ('asbestos', 'Asbestos Register', OPERATIONAL, ['model_dg_asbestos'], ['responsible_person_id']),
    ('asbestos_inspection', 'Asbestos Inspections', OPERATIONAL, ['model_dg_asbestos_inspection'],
     ['asbestos_id.responsible_person_id']),
    ('building', 'Buildings / Sites', CONFIG, ['model_dg_building'], []),
    ('storage_location', 'Storage Locations', CONFIG, ['model_dg_storage_location'], []),
    ('chemical_stage', 'Chemical Register Stages', CONFIG, ['model_dg_chemical_stage'], []),
    ('ppe_type', 'PPE Types', CONFIG, ['model_dg_ppe_type'], []),
    ('storage_class', 'DG Storage Classes', CONFIG, ['model_dg_storage_class'], []),
    ('adg_class', 'ADG Transport Classes', CONFIG, ['model_dg_adg_class'], []),
    ('asbestos_form', 'Asbestos Forms', CONFIG, ['model_dg_asbestos_form'], []),
    ('control_measure', 'Control Measures', CONFIG, ['model_dg_control_measure'], []),
    ('asbestos_remover', 'Asbestos Removalists', CONFIG, ['model_dg_asbestos_remover'], []),
    ('ghs_hazard_class', 'GHS Hazard Classes', CONFIG, ['model_ghs_hazard_class'], []),
    ('ghs_pictogram', 'GHS Pictograms', CONFIG, ['model_ghs_pictogram'], []),
    ('ghs_hazard_statement', 'GHS Hazard Statements', CONFIG, ['model_ghs_hazard_statement'], []),
    ('ghs_precautionary_statement', 'GHS Precautionary Statements', CONFIG,
     ['model_ghs_precautionary_statement'], []),
]

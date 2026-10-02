"""Print Farm access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py print_farm_jobs
"""

APP_NAME = 'Print Farm'
PREFIX = 'print_farm'
CATEGORY = 'module_category_print_farm'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('job', 'Print Jobs', OPERATIONAL, {
        'model_print_job': [],
        'model_print_job_filament': ['job_id.create_uid'],
    }, []),
    ('spool', 'Filament Spools', OPERATIONAL, ['model_print_filament_spool'], []),
    ('restock', 'Restock Orders', OPERATIONAL, {
        'model_print_restock_order': [],
        'model_print_restock_order_line': ['order_id.create_uid'],
    }, []),
    ('printer', 'Printers', OPERATIONAL,
     ['model_print_printer', 'model_print_printer_filament_slot'], []),
    ('filament', 'Filament Catalogue', CONFIG, ['model_print_filament'], []),
]

EXTRA_ACCESS = [
    ('access_assign_printer_wizard', 'model_print_job_assign_printer_wizard', 'group_print_farm_job_view', 'rwcu'),
    ('access_printer_file_wizard', 'model_print_printer_file_wizard', 'group_print_farm_printer_update', 'rwcu'),
    ('access_printer_file_wizard_line', 'model_print_printer_file_wizard_line',
     'group_print_farm_printer_update', 'rwcu'),
    ('access_bambu_auth_wizard', 'model_print_printer_bambu_auth_wizard', 'group_print_farm_printer_update', 'rwcu'),
]

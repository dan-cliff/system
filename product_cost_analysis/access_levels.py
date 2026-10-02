"""Product Cost Analysis access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py product_cost_analysis
"""

APP_NAME = 'Product Cost Analysis'
PREFIX = 'cost'
CATEGORY = 'module_category_product_cost_analysis'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('analysis', 'Product Cost Analyses', OPERATIONAL, {
        'model_product_cost_analysis': [],
        'model_product_cost_analysis_line': ['analysis_id.create_uid'],
    }, []),
]

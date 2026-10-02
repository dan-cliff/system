"""Stocktake access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py stock_stocktake
"""

APP_NAME = 'Stocktakes'
PREFIX = 'stocktake'
CATEGORY = 'base.module_category_supply_chain'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('stocktake', 'Stocktakes', OPERATIONAL, {
        'model_stock_stocktake': ['user_id'],
        'model_stock_stocktake_line': ['stocktake_id.user_id', 'stocktake_id.create_uid'],
    }, []),
]

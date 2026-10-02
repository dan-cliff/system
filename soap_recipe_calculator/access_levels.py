"""Soap Recipe Calculator access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py soap_recipe_calculator
"""

APP_NAME = 'Soap Recipes'
PREFIX = 'soap'
CATEGORY = 'base.module_category_supply_chain'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    ('recipe', 'Soap Recipes', OPERATIONAL, {
        'model_soap_recipe': [],
        'model_soap_recipe_line': ['recipe_id.create_uid'],
    }, []),
]

EXTRA_ACCESS = [
    ('access_soap_recipe_improve_wizard', 'model_soap_recipe_improve_wizard', 'group_soap_recipe_view', 'rwcu'),
]

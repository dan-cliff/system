{
    'name': 'AI - Anthropic Claude Provider',
    'version': '19.0.1.0.0',
    'summary': 'Adds Anthropic Claude as a selectable AI provider in AI settings',
    'category': 'Technical',
    'author': "Cliff's Country Crafts",
    'depends': ['ai', 'ai_app'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/anthropic_auth_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': False,
    'license': 'LGPL-3',
}

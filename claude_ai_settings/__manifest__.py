{
    'name': 'AI Integration Settings',
    'version': '19.0.1.4.0',
    'category': 'Technical',
    'summary': 'Store Claude AI / Google Gemini API keys for other apps in this database to use for AI agent features',
    'description': """
AI Integration Settings
========================
Adds Claude AI and Google Gemini API key fields to Settings > General
Settings > Integrations. Other installed apps can read these via the
`claude_ai_settings.api_key` and `claude_ai_settings.gemini_api_key`
system parameters, so AI agent features don't each need their own
separate setup.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['base_setup'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

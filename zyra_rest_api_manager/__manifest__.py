# -*- coding: utf-8 -*-
{
    'name': "Zyra Rest API Manager",

    'summary': "REST API management with auth, keys, and rate limits",

    'description': """
        Manage REST endpoints with API keys and rate limiting.
        Provides login and registration APIs plus model and custom endpoints.
        Includes UI to enable/disable auth endpoints.
    """,

    'author': "Zyra",
    'website': "https://www.zyra.com",

    'category': 'Tools',
    'license': 'LGPL-3',
    'version': '1.1.0',

    'depends': ['base'],

    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/auth_endpoint_data.xml',
        'views/app_key_views.xml',
        'views/auth_endpoint_views.xml',
        'views/model_endpoint_views.xml',
        'views/custom_endpoint_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
}

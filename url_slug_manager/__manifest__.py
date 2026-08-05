{
    'name': 'URL Slug Manager',
    'version': '19.0.1.0.0',
    'summary': 'Manage meaningful URL paths for custom module actions',
    'description': """
        Provides a settings interface for configuring custom URL slugs on Odoo backend
        actions, replacing generic /odoo/action-XXXX paths with human-readable URLs
        such as /odoo/physical-assets or /odoo/print-jobs.

        Access is restricted to users holding the
        'Technical Configuration - Administrator' security role.

        Pre-populates slug configurations for all installed custom modules
        automatically on first install.
    """,
    'category': 'Technical',
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'web'],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'views/url_slug_config_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}

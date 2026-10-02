# -*- coding: utf-8 -*-
{
    'name': 'Report Builder',
    'version': '19.0.1.1.0',
    'summary': 'Build custom reports from any model with flexible output formats',
    'description': """
Report Builder allows administrators and report authors to design custom reports
from any Odoo model. Features include:
- Multi-model support with related field traversal
- Visual column selection and ordering
- Standard Odoo domain filtering
- Custom menu placement in any app
- Output formats: Excel (.xlsx), CSV, Matrix, PDF
- Matrix reports with configurable axes
- PDF reports with selectable page size and orientation
    """,
    'category': 'Reporting',
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'web', 'mail', 'permission_management'],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/res_lang_data.xml',
        'views/report_builder_views.xml',
        'views/report_builder_column_views.xml',
        'views/report_builder_menu_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'report_builder/static/src/css/report_builder.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['openpyxl', 'reportlab'],
    },
}

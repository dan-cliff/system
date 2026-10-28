{
    'name': 'Development - Organisation Structure',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Bulk update the Organisation of tickets',
    'description': """
Installs automatically when both Development and Organisation Structure are installed.

The tickets' Bulk Update gets the Organisation fields (Division / Business Unit /
Location / Department, as configured in Settings › Organisational Management).
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['dev_management', 'org_structure'],
    'data': [
        'views/dev_ticket_bulk_update_views.xml',
    ],
    'auto_install': True,
    'installable': True,
}

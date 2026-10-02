{
    'name': 'Print Farm Jobs',
    'version': '19.0.1.1.0',
    'summary': '3D Print Farm Job Queue & Printer Management',
    'description': """
        Manage a fleet of 3D printers (Bambu Labs and others) with:
        - Job queue with file attachments (.3mf / .gcode)
        - Filament tracking per printer / AMS slot
        - Automatic printer selection based on required filaments
        - Bambu Labs API integration (local MQTT/FTP and cloud)
    """,
    'category': 'Manufacturing',
    'author': 'Custom',
    'depends': ['base', 'mail', 'product', 'purchase', 'sale'],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/filament_data.xml',
        'data/cron_data.xml',
        'views/print_filament_views.xml',
        'views/print_printer_views.xml',
        'views/print_job_views.xml',
        'views/print_spool_views.xml',
        'views/print_restock_views.xml',
        'wizard/assign_printer_wizard_views.xml',
        'wizard/printer_files_wizard_views.xml',
        'wizard/bambu_auth_wizard_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'images': ['static/description/icon.png'],
}

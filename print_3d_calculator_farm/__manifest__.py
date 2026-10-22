{
    'name': '3D Print Calculator - Print Farm',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Read print job files with the 3D Print Calculator and consume filament '
               'from inventory when print jobs are completed.',
    'description': """
Connects 3D Print Calculator with Print Farm Jobs:

* A print job's file is read into a 3D print estimate (filaments, weights, time).
* With "Consume Filament on Completion" enabled in the Print Farm settings,
  completing a job takes the filament it used out of stock, using each
  material's filament product.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['print_3d_calculator', 'print_farm_jobs', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/print_job_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

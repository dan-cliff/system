# -*- coding: utf-8 -*-
{
    'name': 'Checklists - Assets',
    'version': '19.0.1.1.0',
    'category': 'Productivity',
    'summary': 'Pick the asset a checklist is for, from Asset Management',
    'description': """
        Installs automatically when both Checklists and Asset Management are
        installed.

        On each Checklist Template (Features tab):

        - Asset Selector: turns on an asset field on that template's checklists
        - Asset Required: the asset must be filled in
        - Asset Filter: a filter (like Odoo's filter builder) limiting which
          assets can be picked
        - Asset Selector Label: renames the asset field on that template's
          checklists (e.g. "Vehicle")

        The Public URL Builder can set the asset of the checklists submitted
        with a link (within the template's Asset Filter).
    """,
    'author': 'Custom',
    'depends': ['checklists', 'asset_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/checklist_template_views.xml',
        'views/checklist_views.xml',
        'views/checklist_public_url_wizard_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

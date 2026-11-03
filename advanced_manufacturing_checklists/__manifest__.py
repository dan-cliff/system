# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing - Checklists',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'QA checklists from the Work Centre app, linked to the product and lot produced',
    'description': """
Installs automatically when both Manufacturing and Checklists are installed.

- Settings › Manufacturing › Quality Checks: choose the Checklist Groups used
  for QA checks.
- When any are chosen, workers can start QA checklists from those groups'
  templates on the Work Centre app (QA, on each work order), online or offline.
- Checklists created there are filled in with what the work order knows:
  questions picking a product, lot / serial number, manufacturing order, work
  order, work centre or employee, and questions named like them (e.g.
  "Product", "Batch Number", "Operator", "Quantity", "Production Date").
- Each QA checklist is linked to its manufacturing order, work order, work
  centre, worker, the product made and, for products tracked by lot / serial
  number, the lot produced (also when the lot is only set when the order is
  produced). Manufacturing orders, lots and products get a QA Checks button.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_manufacturing', 'checklists'],
    'data': [
        'views/checklist_views.xml',
        'views/mrp_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

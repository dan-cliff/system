# -*- coding: utf-8 -*-
{
    'name': 'Checklists',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'General-purpose checklists built from templates, grouped into Checklist Groups',
    'description': """
        Checklists

        - Checklist templates with configurable questions
        - Question types: Text, Text Area, Number, Integer, Date, Datetime and Buttons (with your own button values)
        - Checklist Groups organise templates; the templates list filters by group from its side panel
        - Checklists copy the template's questions so past checklists keep the questions they were answered against
        - Templates export to JSON (several at once as a .zip) and import into this or other databases.
          Every template, question and button value carries a hidden GUID: importing updates the
          records whose GUID already exists and creates the rest, so a file can be imported straight
          into a template to bulk-update its questions
        - Checklists print to PDF

        With Organisation Structure installed, checklists get the Division / Business Unit /
        Location / Department fields automatically (see org_structure).
    """,
    'author': 'Custom',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/checklist_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/checklist_sequence_data.xml',
        'report/checklist_report.xml',
        'wizard/checklist_template_import_wizard_views.xml',
        'views/checklist_group_views.xml',
        'views/checklist_template_views.xml',
        'views/checklist_views.xml',
        'data/checklist_template_actions.xml',
        'views/res_config_settings_views.xml',
        'views/checklist_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'checklists/static/src/checklist_checks/*',
            'checklists/static/src/colour_badge/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

# -*- coding: utf-8 -*-
{
    'name': 'Checklists',
    'version': '19.0.1.8.0',
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
        - Public Submission (per template): a login-free link anyone can fill the
          checklist in from. They give their First Name, Last Name and Email or
          Phone Number instead of the Completed By, Asset, Company and
          Organisation fields; the checklist is saved as Completed, with the
          contact that has their email (or a new contact) as its Completed By
        - Public URL Builder: links that fill in chosen contact details and
          answers from their query string, optionally locked (read-only). Links
          are signed, can be built for any combination of values and used for
          any number of submissions; "New Link" on the template retires them all

        With Organisation Structure installed, checklists get the Division / Business Unit /
        Location / Department fields automatically (see org_structure).
    """,
    'author': 'Custom',
    'depends': ['base', 'base_setup', 'mail', 'phone_validation'],
    'data': [
        'security/checklist_security.xml',
        'security/ir.model.access.csv',
        'security/checklist_rules.xml',
        'security/checklist_public_security.xml',
        'data/res_lang_data.xml',
        'data/checklist_sequence_data.xml',
        'report/checklist_report.xml',
        'wizard/checklist_template_import_wizard_views.xml',
        'wizard/checklist_ai_wizard_views.xml',
        'wizard/checklist_public_url_wizard_views.xml',
        'views/checklist_group_views.xml',
        'views/checklist_template_views.xml',
        'views/checklist_views.xml',
        'views/checklist_public_templates.xml',
        'data/checklist_template_actions.xml',
        'views/res_config_settings_views.xml',
        'views/checklist_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'checklists/static/src/checklist_checks/*',
            'checklists/static/src/colour_badge/*',
            'checklists/static/src/answer_widgets/*',
            'checklists/static/src/ai_generator/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

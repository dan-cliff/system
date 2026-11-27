# -*- coding: utf-8 -*-
{
    'name': "Sign'r",
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Send contracts, order forms and other documents made from Word templates for digital signature',
    'description': """
        Sign'r

        - Templates are written in Microsoft Word with merge codes where a record's
          values go, either typed (``{{ job_id.name }}``) or as Word merge fields
          (``MERGEFIELD job_id.name``), then uploaded
        - Each template is for an app and one of its models (e.g. Employees >
          Employee); the Merge Fields tab lists every code that model offers, and
          follows links to related records (e.g. the employee's Job Position)
        - The codes in an uploaded document are checked against the model, and
          requests can't be sent while one is wrong
        - Table rows repeat for list fields (e.g. one row per order line); dates
          come out as dd/mm/yyyy; pictures and signatures are placed in the document
        - Signers come from the record (e.g. the employee and their manager), are
          fixed contacts, the sender, or picked when sending; they sign in order or
          all at once
        - Sign Requests record the template, the record they were raised from (its
          app, model and record), who they were sent to, and when they were sent and
          signed
        - Each signer gets a private link, reads the PDF and signs online (or
          declines with a reason); the signed PDF, with a signing certificate, is
          emailed to everyone and filed on the record
        - Settings > Sign'r > Integrations add Request Signature and Sign Requests
          buttons to Talent applications, CRM opportunities and contracts, sales
          orders, employees and their contracts, incidents and return to work cases

        PDFs are made with LibreOffice when the server has it (closest to the Word
        layout), otherwise from a simplified copy of the document.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base_setup', 'mail', 'portal', 'hr'],
    'external_dependencies': {'python': ['lxml', 'Pillow']},
    'data': [
        'security/signr_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/signr_data.xml',
        'data/mail_template_data.xml',
        'report/signr_certificate_report.xml',
        'views/signr_template_views.xml',
        'views/signr_request_views.xml',
        'views/signr_portal_templates.xml',
        'views/signr_menus.xml',
        'data/signr_sample_template_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'signr/static/src/merge_fields/*',
        ],
        'web.assets_frontend': [
            'signr/static/src/scss/portal.scss',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Mailchimp Transactional Email Service',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Send and receive all Odoo email through Mailchimp Transactional (Mandrill)',
    'description': """
Mailchimp Transactional Email Service
=====================================
Adds a "Mailchimp Transactional Email Service" toggle to Settings > General
Settings > Emails. When enabled:

* every outgoing email is sent through the Mailchimp Transactional
  (formerly Mandrill) ``messages/send-raw`` API instead of SMTP;
* incoming email arrives through Mandrill inbound routes, which are created,
  updated and removed automatically as mail aliases change, and is delivered
  to Odoo's mail gateway by a webhook plus a cron;
* the reply-to address can be set per model, with an overall fallback;
* record details can be sent as Mandrill metadata and embedded in the
  reply-to address so replies are logged against the record they answer;
* every email sent or received through the service is kept in a log.
""",
    'author': 'Cliffs Country Crafts',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/mandrill_mail_log_views.xml',
        'views/mandrill_reply_route_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

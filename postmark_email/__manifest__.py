{
    'name': 'Postmark Email Service',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Send and receive all Odoo email through the Postmark API',
    'description': """
Postmark Email Service
======================
Adds a "Postmark Email Service" setting to Settings > General Settings >
Emails. When it is on, Odoo sends every email through the Postmark Email
API (https://postmarkapp.com/developer) instead of SMTP, and receives
email, bounces and spam complaints through Postmark webhooks. Turning it
on turns off Use Custom Email Servers, Use an Outlook Server and Use a
Gmail Server.

* Server API Token, sender domains, default message stream and a fallback
  reply-to address.
* Reply Addresses: a reply-to address and message stream per model (e.g.
  invoices reply to invoices@...). With "Create Message Streams from
  Aliases", every email alias gets one automatically, and its own Postmark
  message stream, created and renamed with the alias.
* Link Replies to Records: the record an email was sent from goes into the
  email's Postmark metadata and its reply-to address (reply+<record>@...),
  so a reply is logged on that record (e.g. a reply to an invoice email is
  logged on the invoice). Replies are also matched on the Message-IDs of
  the emails sent.
* Bounces and spam complaints are flagged on the email log, the chatter
  message (bounced notification), the contact's bounce count and the
  record; spam complainers can be blacklisted.
* Postmark Email Log (Settings > Technical > Email, or from the setting):
  every email sent or received, its stream, status and linked record.
  Incoming emails that could not be routed can be processed again.
* "Sync with Postmark" checks the token, loads the message streams and
  registers the inbound, bounce, spam complaint and delivery webhooks
  (HTTP basic auth).
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/postmark_message_stream_data.xml',
        'views/postmark_message_stream_views.xml',
        'views/postmark_reply_rule_views.xml',
        'views/postmark_email_log_views.xml',
        'views/postmark_menus.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

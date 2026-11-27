{
    'name': 'Helpdesk',
    'version': '19.0.2.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Track, prioritise and solve customer support tickets',
    'description': """
Helpdesk
========
Modelled on the Odoo Enterprise Helpdesk app.

* Helpdesk teams, each with its own members, ticket stages, working hours
  and email alias: an email to the alias opens a ticket, and replies are
  threaded onto it.
* Tickets with customer, priority (stars), type, tags, assignee and a
  kanban board by stage. Stages marked "Closing Stage" (folded) close the
  ticket.
* Automatic assignment per team: manual, round robin (each member gets the
  same number of tickets) or balanced (each member has the same number of
  open tickets).
* SLA policies per team: reach a stage within so many working hours, for
  tickets of a given priority, type, tag or customer. Each ticket shows its
  SLA deadlines, and failed SLAs are highlighted and can be filtered.
* Email templates per stage (e.g. an acknowledgement on New) and customer
  satisfaction ratings requested when a ticket is solved.
* Auto-close: move tickets left untouched for a number of days to a closing
  stage.
* Customer portal: customers see and reply to their tickets at /my/tickets
  and can close them. Teams can publish a "Submit a Ticket" form at
  /helpdesk.
* Overview dashboard per team, ticket and SLA analysis, customer ratings.
* Ticket types, tags and stages are managed under Configuration.
* Ticket metrics: company, team, products, source (email, website form, Help
  Centre, direct entry, ...), customer sentiment, date raised, days open, days
  to resolution and agent.
* AI triage: when a Claude or Gemini key is set in General Settings, new
  tickets are sent to the AI in the background to fill in missing details
  (team, type, tags, priority, products), estimate the customer sentiment from
  the tone of the ticket and recommend corrective actions. "Analyse with AI"
  on a ticket runs it again on demand.
* Dashboard: outstanding tickets by company and team, the user's own
  outstanding tickets, and the average customer sentiment of their tickets
  over the last 12 months, year to date and last 30 days.
* Permissions per CLAUDE.md: a privilege per ticket permission (Create Only,
  Create and Edit Own / My Team / All, View All, Delete Own / All) plus the
  Helpdesk Administrator; standard roles ship in helpdesk_management_permission.
""",
    'author': 'Cliffs',
    'license': 'LGPL-3',
    'depends': ['mail', 'portal', 'rating', 'resource', 'product', 'hr'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/helpdesk_sequence.xml',
        'data/mail_message_subtype_data.xml',
        'data/mail_template_data.xml',
        'data/helpdesk_data.xml',
        'data/helpdesk_option_data.xml',
        'data/helpdesk_cron.xml',
        'views/helpdesk_option_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/helpdesk_sla_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_team_views.xml',
        'views/res_partner_views.xml',
        'views/helpdesk_portal_templates.xml',
        'report/helpdesk_report_views.xml',
        'views/helpdesk_dashboard_views.xml',
        'views/helpdesk_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'helpdesk_management/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
}

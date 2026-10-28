{
    'name': 'Development - Helpdesk',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Create development tickets straight from Helpdesk tickets',
    'description': """
        Installs automatically when both Development and Helpdesk are installed.

        - "Create Dev Tickets" on a Helpdesk ticket opens a form to raise one or more
          development tickets (bug, story, task, ...) from it, prefilled from the Helpdesk
          ticket, or to link existing ones
        - Helpdesk and development tickets show each other (a Dev Tickets smart button and a
          Helpdesk tab)
        - When a linked development ticket is done, or its release reaches Core Release, the
          Helpdesk ticket gets an internal note so the agent can tell the customer
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['dev_management', 'helpdesk_management'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/dev_ticket_from_helpdesk_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/dev_ticket_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

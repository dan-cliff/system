{
    'name': 'Accounting - Actions',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Accounting follow-ups and payment warnings in the Actions app',
    'description': """
        Installs automatically when both Accounting and Actions are installed.

        - The follow-up actions of customers (the manual actions of the
          follow-up levels, and the reminders that could not be emailed) and
          the warnings of failed recurring payments are stored in Actions (one
          table for every app's actions) instead of activities. Installing this
          module moves the open ones into Actions; uninstalling it moves them
          back to activities.
        - Customers and recurring payments get an Actions button
        - Accounting › Actions opens Actions filtered to Accounting (remove the
          filter to see every action)
        - Paying everything closes the follow-up actions of a customer, and a
          recurring payment that pays again closes its warnings
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounting', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_accounting_security.xml',
        'views/advanced_action_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

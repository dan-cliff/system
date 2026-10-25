{
    'name': 'CRM - Subscriptions',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Subscriptions (subscription_oca) on CRM opportunities',
    'description': """
        Installs automatically when both CRM (modern_crm) and Subscription
        management (subscription_oca) are installed.

        Confirming an opportunity's quote (by hand, or when its contract is
        fully signed) creates a subscription for each subscribable product, as
        subscription_oca does for every sales order. This module shows those
        subscriptions on the opportunity (a Subscriptions button) and marks
        recurring products on its product lines.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_crm', 'subscription_oca'],
    'data': [
        'views/modern_crm_opportunity_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

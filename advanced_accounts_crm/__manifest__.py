{
    'name': 'Remap CRM Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'CRM opportunities, contact roles, contracts and leads use Accounts and Contacts',
    'description': """
        Switched on in Settings > Advanced Accounts. In CRM:

        - Opportunities pick an Account and a Primary Contact (only that
          Account's Contacts) in place of their Account and Primary Contact
          partners; Contact Roles pick Contacts of the opportunity's Account.
        - Contracts pick an Account.
        - Leads pick an existing Account and Contact.
        - CRM's Customers > Accounts and Contacts menus open Advanced Accounts.

        The partner fields keep following the Account and Contact, so quotes,
        contracts and their signers work as before.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'modern_crm'],
    'data': [
        'views/modern_crm_views.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}

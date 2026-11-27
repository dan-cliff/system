{
    'name': 'Remap Property Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Services/Property',
    'summary': 'Landlords, tenants, agents and suppliers in Property use Accounts and Contacts',
    'description': """
        Switched on in Settings > Advanced Accounts. In Property:

        - Properties pick their Landlord and Managing Agent from Accounts.
        - Leases pick their Landlord / Tenant and Agent from Accounts.
        - Contracts pick their Supplier from Accounts, and the supplier's
          Contact from that Account's Contacts.

        The partner fields they stand in for are kept in step, so everything
        reading them works as before; each shows only while it holds a partner
        that isn't an Account or Contact (e.g. one of our own users).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'property_management'],
    'data': [
        'views/property_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

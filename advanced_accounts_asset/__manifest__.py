{
    'name': 'Remap Asset Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Operations/Assets',
    'summary': 'Asset Supplier and Manufacturer use Accounts; Owner and Assigned To use Contacts',
    'description': """
        Switched on in Settings > Advanced Accounts. In Asset Management:

        - Assets pick their Supplier, Manufacturer and Software Supplier from
          Accounts, and their Owner and Assigned To from Contacts.
        - Maintenance logs pick their Supplier from Accounts.

        Supplier, Manufacturer, Software Supplier and Owner keep their partner
        fields in step, so the asset portal and reports work as before. Assigned
        To used to be an employee: the employee field is kept, and shows as
        "Assigned To (Employee)" on assets that have one and no Contact yet.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'asset_management'],
    'data': [
        'views/asset_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

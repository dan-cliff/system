{
    'name': 'CRM - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Standard Permission Management roles for the CRM (modern_crm)',
    'description': """
        Installs automatically when both CRM (modern_crm) and Permission
        Management are installed, and adds these roles:

        - CRM – Administrator: everything, including deleting any lead,
          opportunity or contract, every workflow action and Configuration
        - CRM – Manager: create and edit their own and their team's leads,
          opportunities and contracts
        - CRM – Employee: create and edit their own leads, opportunities and
          contracts
        - CRM – Sales Representative: as Employee, plus creating quotes and
          sending contracts for signature
        - CRM – Sales Operations: view every lead, work every opportunity and
          contract, activate contracts, confirm sales orders and create invoices
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['modern_crm', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

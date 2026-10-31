# -*- coding: utf-8 -*-
{
    'name': 'Purchasing - Personnel',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Purchase',
    'summary': "Employees' spend delegations and approvals by their 1st to 4th Up Managers",
    'description': """
        Installs automatically when both Purchasing and Personnel are installed.

        - Purchases Rules tab on employees: their Spend Level Delegation (or a
          custom limit), the dates it is valid between, notes, and their 1st to
          4th Up Managers from the org chart. Only users with Spend Delegations:
          Manage can change it.
        - Orders within the buyer's delegation need no approval. Above it, the
          order goes to the buyer's Up Manager that the order's Spend Level names
          (at least their 1st Up Manager), skipping managers without a user or
          without the Purchase Orders: Approve permission, and (Settings ›
          Purchasing › Escalate Approvals) managers whose own delegation is below
          the order total. When no manager up to the 4th qualifies, the order goes
          to the users with Approve Any.
        - Create and Edit My Team covers the orders of the employees under theirs
          in the org chart.
        - Spend Levels show the employees holding them.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_purchasing', 'advanced_hr'],
    'data': [
        'security/advanced_purchasing_hr_security.xml',
        'views/hr_employee_views.xml',
        'views/spend_level_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

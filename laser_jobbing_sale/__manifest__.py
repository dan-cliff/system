# -*- coding: utf-8 -*-
{
    'name': 'Laser Jobbing - Sales',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Laser jobs for the personalised products on sales orders',
    'description': """
        Installs automatically with Laser Jobbing and Sales.

        - Every order line of a product with a Laser Template gets a laser job,
          made when the order is confirmed (or earlier with the Personalise
          button), with the order's customer, quantity and commitment date.
        - Confirming the order confirms the jobs that are filled in; jobs still
          missing details stay in Draft with a note on the order.
        - Changing a line's quantity updates its job; cancelling the order
          cancels its jobs that aren't done.
        - Laser Jobs smart button on orders, and the order on each job.
    """,
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['laser_jobbing', 'sale'],
    'data': [
        'views/sale_order_views.xml',
        'views/laser_job_views.xml',
    ],
    'auto_install': True,
    'installable': True,
}

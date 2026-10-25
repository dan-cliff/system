{
    'name': 'Live Sales Counter - Display Screens',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Show a Live Sales Counter full screen on a Display Screen Node (IoT Interfaces)',
    'description': """
        Installs automatically when Live Sales Counter and the Display Screen
        Nodes (IoT Interfaces, through Embroidery Jobbing) are installed.

        - A Display Screen Node can show a Live Sales Counter instead of an
          Embroidery status board: choose it under IoT Interfaces > Nodes >
          Display Screens.
        - The screen switches within a few seconds when its content changes.
        - The Node's requests are signed with its rolling key, so a private
          counter shows on the screen without an Odoo login.
        - Each counter shows the screens showing it.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['live_sales_counter', 'embroidery_jobbing'],
    'data': [
        'views/iot_node_views.xml',
        'views/live_counter_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

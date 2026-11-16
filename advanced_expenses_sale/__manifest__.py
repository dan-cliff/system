{
    'name': 'Expenses - Sales',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': "Re-invoice expenses to a customer's sales order",
    'description': """
        Switched on in Settings › Expenses › Integrations › Re-invoice to Customers
        (shown when Sales is installed), and installed with Expenses when it takes
        over from Odoo's Expenses app with Sales Expense installed.

        - Expenses get a Customer to Re-invoice: a confirmed sales order
        - Approving the expense adds it to the order as a line at its cost, to be
          invoiced with the order; resetting the expense sets the line's quantity
          to 0 (unless it has been invoiced)
        - Expense Categories can choose the product used on the order line;
          without one, the "Re-invoiced Expense" product is used
        - Sales orders show their expenses
        - The sales orders of Odoo's Expenses are kept on the copied expenses
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_expenses', 'sale'],
    'data': [
        'data/product_data.xml',
        'views/expense_category_views.xml',
        'views/advanced_expense_views.xml',
        'views/sale_order_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

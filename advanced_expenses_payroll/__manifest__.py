{
    'name': 'Expenses - Payroll',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Reimburse approved expenses on the next payslip',
    'description': """
        Switched on in Settings › Expenses › Integrations › Reimburse through
        Payroll (shown when Payroll is installed).

        - Computing a draft payslip adds the employee's approved expenses that
          they paid themselves (dated up to the end of the pay period, not yet
          reimbursed or billed) as Reimbursement lines, one per expense, untaxed
        - Approving an expense refreshes the employee's draft payslips
        - Marking the pay run as paid marks the expenses as Paid on the payment
          date; cancelling the pay run, or resetting a paid one, releases them
        - Expenses show their payslip, payslips list their expenses
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_expenses', 'advanced_payroll'],
    'data': [
        'views/advanced_expense_views.xml',
        'views/payroll_slip_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

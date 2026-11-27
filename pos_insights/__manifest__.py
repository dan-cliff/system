# Copyright 2026 Cliff's Country Crafts
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

{
    "name": "POS Insights",
    "version": "19.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Print the current session's reports from inside the POS",
    "description": """
POS Insights
============
Lets cashiers print reports for the POS session they are working in,
without opening the backend.

Users in the "POS Insights" group get a "Reports" button in the POS
Actions menu (the "..." button on the product screen). It offers three
PDF reports, all limited to the current session:

- Orders: every order in the session, plus a sales summary by product
  (the in-POS stand-in for the backend Reporting > Orders analysis).
- Sales Details: the standard Sales Details report, run from the
  session's opening time until now for this POS.
- Session Report: the standard Session Report for this session.

With employee login (pos_hr), POS Insights - Employees (installed
automatically) checks the permission of the user linked to the logged-in
cashier employee instead of the user who opened the POS.
""",
    "author": "Cliff's Country Crafts",
    "website": "https://github.com/dan-cliff/system",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/pos_insights_security.xml",
        "report/pos_insights_orders_report.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_insights/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
}

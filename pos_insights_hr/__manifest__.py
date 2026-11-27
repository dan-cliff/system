# Copyright 2026 Cliff's Country Crafts
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

{
    "name": "POS Insights - Employees",
    "version": "19.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "POS Insights access follows the logged-in cashier employee",
    "description": """
POS Insights - Employees
========================
When a POS uses employee login (pos_hr), the "Reports" button and the
reports themselves are controlled by the "POS Insights" permission of
the user linked to the employee who is logged in as cashier, not by
the Odoo user who opened the POS. An employee with no linked user has
no access.

Installed automatically when both POS Insights and POS HR are installed.
""",
    "author": "Cliff's Country Crafts",
    "website": "https://github.com/dan-cliff/system",
    "license": "LGPL-3",
    "depends": ["pos_insights", "pos_hr"],
    "installable": True,
    "auto_install": True,
    "application": False,
}

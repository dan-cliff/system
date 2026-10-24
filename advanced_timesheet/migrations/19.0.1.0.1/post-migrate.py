# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The app was renamed from "Advanced Timesheets" to "Timesheets". Its
    category is noupdate data, so rename it here unless an admin changed it."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    category = env.ref('advanced_timesheet.module_category_advanced_timesheet', raise_if_not_found=False)
    if category and category.name == 'Advanced Timesheets':
        category.write({
            'name': 'Timesheets',
            'description': 'Weekly, fortnightly or monthly timesheets, with optional manager approval.',
        })

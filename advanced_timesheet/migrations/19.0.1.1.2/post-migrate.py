# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The app was renamed from "Advanced Timesheets" to "Timesheets". Its
    category and the scheduled actions of its add-ons are noupdate data, so
    rename them here unless an admin changed them."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    category = env.ref('advanced_timesheet.module_category_advanced_timesheet', raise_if_not_found=False)
    if category and category.name == 'Advanced Timesheets':
        category.write({
            'name': 'Timesheets',
            'description': 'Weekly, fortnightly or monthly timesheets, with optional manager approval.',
        })
    crons = env['ir.cron'].with_context(active_test=False).search([('name', '=like', 'Advanced Timesheets:%')])
    for cron in crons:
        cron.name = 'Timesheets:' + cron.name[len('Advanced Timesheets:'):]

# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

OLD = 'Advanced Timesheets'
NEW = 'Timesheets'


def migrate(cr, version):
    """The app was renamed from "Advanced Timesheets" to "Timesheets". The roles
    are noupdate data, so rename them here (keeping any name an admin changed)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ('admin', 'manager', 'employee', 'approver'):
        role = env.ref('advanced_timesheet_permission.role_advanced_timesheet_%s' % xmlid, raise_if_not_found=False)
        if not role:
            continue
        vals = {}
        if role.name and role.name.startswith(OLD + ' – '):
            vals['name'] = NEW + role.name[len(OLD):]
        if role.description and OLD in role.description:
            vals['description'] = role.description.replace(OLD, NEW)
        if vals:
            role.write(vals)

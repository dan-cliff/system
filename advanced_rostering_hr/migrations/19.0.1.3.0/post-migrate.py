# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Leave requests take their Organisation from the employee: bring the
    existing ones in line."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rostering.leave'].with_context(active_test=False).search([
        ('employee_id', '!=', False),
    ])._sync_org_from_employee()

# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Leave requests take their Organisation from the employee, and public
    holiday jurisdictions follow the employee's Work Address (no longer the
    private address): bring existing records in line."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rostering.leave'].with_context(active_test=False).search([
        ('employee_id', '!=', False),
    ])._sync_org_from_employee()
    env['hr.employee']._rostering_apply_address_jurisdictions()

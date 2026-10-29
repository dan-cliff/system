# -*- coding: utf-8 -*-
from odoo import models

# Set (as this object, which RPC calls can't send) while Odoo writes a new
# employee's details on the version it just created for it.
_NEW_EMPLOYEE_VERSION = object()


class HrVersion(models.Model):
    _inherit = 'hr.version'

    # Version fields edited on the employee are recorded in the employee's
    # Audit Trail; chatter tracking is not used.
    def _track_get_fields(self):
        return set()

    def write(self, vals):
        # Creating an employee writes its details on its new version (hr's
        # hr.employee._create): part of creating, so the Create permissions
        # cover it, Create Only included.
        if self.env.context.get('personnel_new_employee_version') is _NEW_EMPLOYEE_VERSION:
            return super(HrVersion, self.sudo()).write(vals)
        return super().write(vals)

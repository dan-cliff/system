# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rostering_employee_jurisdictions = fields.Boolean(
        string='Public Holiday Jurisdictions on Employees',
        config_parameter='advanced_rostering.employee_jurisdictions',
        help='Choose on each employee (Payroll tab) which public holiday jurisdictions apply to them. The '
             'Country and State of their private address are picked automatically.',
    )

    def set_values(self):
        was_on = self.env['hr.employee']._rostering_jurisdictions_switched_on()
        super().set_values()
        if not was_on and self.env['hr.employee']._rostering_jurisdictions_switched_on():
            self.env['hr.employee']._rostering_apply_address_jurisdictions()

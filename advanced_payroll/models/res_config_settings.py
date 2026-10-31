# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .payroll_pay_frequency import DEFAULT_PERIOD_START
from .payroll_slip import HOURS_SOURCES

# Payroll country apps by ISO code, like Accounting's fiscal localisations.
COUNTRY_MODULES = {
    'AU': 'advanced_payroll_au',
    'NZ': 'advanced_payroll_nz',
    'US': 'advanced_payroll_us',
    'CA': 'advanced_payroll_ca',
}
# Feature switches: the app each one works with, and the bridge module it installs.
FEATURE_APPS = {
    'advanced_accounting': 'module_advanced_payroll_accounting',
    'advanced_hr': 'module_advanced_payroll_hr',
    'advanced_attendance': 'module_advanced_payroll_attendance',
    'advanced_timesheet': 'module_advanced_payroll_timesheet',
    'advanced_rostering': 'module_advanced_payroll_rostering',
}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Payroll countries
    module_advanced_payroll_au = fields.Boolean(string='Australia')
    module_advanced_payroll_nz = fields.Boolean(string='New Zealand')
    module_advanced_payroll_us = fields.Boolean(string='USA')
    module_advanced_payroll_ca = fields.Boolean(string='Canada')

    # Pay periods and hours
    payroll_period_start = fields.Date(
        string='Weekly Periods Count From',
        help='Weekly and fortnightly pay periods start on this date and every week or fortnight after '
             '(and before) it, so it also sets the day the pay week starts.',
    )
    payroll_hours_source = fields.Selection(
        HOURS_SOURCES, string='Pay Hours From', default='standard',
        config_parameter='advanced_payroll.hours_source',
        help='Where the hours of hourly employees come from. Salaried employees are paid their salary.',
    )

    # Cross-module feature switches, each shown only when its app is installed.
    module_advanced_payroll_accounting = fields.Boolean(string='Accounting')
    module_advanced_payroll_hr = fields.Boolean(string='Personnel')
    module_advanced_payroll_attendance = fields.Boolean(string='On Site')
    module_advanced_payroll_timesheet = fields.Boolean(string='Advanced Timesheets')
    module_advanced_payroll_rostering = fields.Boolean(string='Rostering')
    payroll_advanced_accounting_installed = fields.Boolean(compute='_compute_payroll_apps_installed')
    payroll_advanced_hr_installed = fields.Boolean(compute='_compute_payroll_apps_installed')
    payroll_advanced_attendance_installed = fields.Boolean(compute='_compute_payroll_apps_installed')
    payroll_advanced_timesheet_installed = fields.Boolean(compute='_compute_payroll_apps_installed')
    payroll_advanced_rostering_installed = fields.Boolean(compute='_compute_payroll_apps_installed')

    def _compute_payroll_apps_installed(self):
        installed = set(self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(FEATURE_APPS)),
            ('state', 'in', ('installed', 'to upgrade')),
        ]).mapped('name'))
        for settings in self:
            for app in FEATURE_APPS:
                settings[f'payroll_{app}_installed'] = app in installed

    @api.model
    def get_values(self):
        res = super().get_values()
        res['payroll_period_start'] = self.env['payroll.pay.frequency']._period_anchor()
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'advanced_payroll.period_start',
            fields.Date.to_string(self.payroll_period_start or DEFAULT_PERIOD_START),
        )

# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .rostering_tools import CYCLES, DEFAULT_PERIOD_START, get_period_anchor

# Feature switches: the app each one works with, and the bridge module it installs.
FEATURE_APPS = {
    'advanced_hr': 'module_advanced_rostering_hr',
    'advanced_attendance': 'module_advanced_rostering_attendance',
    'advanced_timesheet': 'module_advanced_rostering_timesheet',
}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rostering_cycle = fields.Selection(
        CYCLES, string='Publish Rosters', default='weekly', required=True,
        config_parameter='advanced_rostering.cycle',
        help='How much time each roster covers. Existing rosters and templates keep their dates and weeks.',
    )
    # Settings cannot keep a Date in a system parameter by themselves: see get/set_values.
    rostering_period_start = fields.Date(
        string='Periods Count From',
        help='Weekly and fortnightly rosters start on this date and every week or fortnight after (and '
             'before) it, so it also sets the day the roster week starts.',
    )
    rostering_notify_publish = fields.Boolean(
        string='Notify Staff on Publishing', config_parameter='advanced_rostering.notify_publish',
        help='When a roster is published, send everyone on it a notification.',
    )

    rostering_leave_hours_per_day = fields.Float(
        string='Full Day Hours', default=7.6, config_parameter='advanced_rostering.leave_hours_per_day',
        help='Hours of a whole day of leave (with Personnel, the Full Time Equivalent of the company\'s '
             'working hours is used instead).',
    )

    # Public holidays
    rostering_holiday_import = fields.Boolean(
        string='Import Public Holidays', config_parameter='advanced_rostering.holiday_import',
        help='Fill the Public Holidays library automatically from Nager.Date (date.nager.at), with the '
             'country and states each holiday applies to. Checked weekly for this year and next.',
    )
    rostering_holiday_country_ids = fields.Many2many(
        related='company_id.rostering_holiday_country_ids', readonly=False)
    rostering_holiday_pay_multiplier = fields.Float(
        string='Default Pay Multiplier', digits=(16, 2), default=1.0,
        config_parameter='advanced_rostering.holiday_pay_multiplier',
        help='Pay multiplier given to new public holidays (standard pay × this). Each holiday can be changed.',
    )

    # Cross-module feature switches, each shown only when its app is installed.
    module_advanced_rostering_hr = fields.Boolean(string='Personnel')
    module_advanced_rostering_attendance = fields.Boolean(string='On Site')
    module_advanced_rostering_timesheet = fields.Boolean(string='Advanced Timesheets')
    rostering_advanced_hr_installed = fields.Boolean(compute='_compute_rostering_apps_installed')
    rostering_advanced_attendance_installed = fields.Boolean(compute='_compute_rostering_apps_installed')
    rostering_advanced_timesheet_installed = fields.Boolean(compute='_compute_rostering_apps_installed')

    def _compute_rostering_apps_installed(self):
        installed = set(self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(FEATURE_APPS)),
            ('state', 'in', ('installed', 'to upgrade')),
        ]).mapped('name'))
        for settings in self:
            for app in FEATURE_APPS:
                settings[f'rostering_{app}_installed'] = app in installed

    @api.model
    def get_values(self):
        res = super().get_values()
        res['rostering_period_start'] = get_period_anchor(self.env)
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'advanced_rostering.period_start',
            fields.Date.to_string(self.rostering_period_start or DEFAULT_PERIOD_START),
        )

    def action_rostering_import_holidays(self):
        self.ensure_one()
        return self.env['rostering.public.holiday'].action_import_now()

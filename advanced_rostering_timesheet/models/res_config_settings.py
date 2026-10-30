# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rostering_leave_hours_per_day = fields.Float(
        string='Leave Hours per Day', default=7.6, config_parameter='advanced_rostering.leave_hours_per_day',
        help='Hours filled in on a timesheet for a weekday of approved leave with no shifts rostered '
             '(days with shifts use their paid hours).',
    )

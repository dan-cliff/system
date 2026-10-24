# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .advanced_timesheet import DEFAULT_PERIOD_START, PERIOD_TYPES


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advanced_timesheet_period_type = fields.Selection(
        PERIOD_TYPES, string='Submit Timesheets', default='weekly', required=True,
        config_parameter='advanced_timesheet.period_type',
        help='How much time each timesheet covers, and so how many weeks its grid shows. '
             'Existing timesheets keep their dates.',
    )
    # Settings cannot keep a Date in a system parameter by themselves: see get/set_values.
    advanced_timesheet_period_start = fields.Date(
        string='Periods Count From',
        help='Weekly and fortnightly timesheets start on this date and every week or fortnight '
             'after (and before) it, so it also sets the day the week starts.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res['advanced_timesheet_period_start'] = self.env['advanced.timesheet']._get_period_anchor()
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'advanced_timesheet.period_start',
            fields.Date.to_string(self.advanced_timesheet_period_start or DEFAULT_PERIOD_START),
        )

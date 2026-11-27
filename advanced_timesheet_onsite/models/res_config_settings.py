# -*- coding: utf-8 -*-
from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def set_values(self):
        Attendance = self.env['advanced.attendance']
        was_enabled = Attendance._advanced_timesheet_sync_enabled()
        super().set_values()
        if not was_enabled and Attendance._advanced_timesheet_sync_enabled():
            Attendance._advanced_timesheet_sync_missing()

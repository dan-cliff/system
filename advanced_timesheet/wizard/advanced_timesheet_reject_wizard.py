# -*- coding: utf-8 -*-
from odoo import fields, models


class AdvancedTimesheetRejectWizard(models.TransientModel):
    _name = 'advanced.timesheet.reject.wizard'
    _description = 'Send a Timesheet Back'

    timesheet_id = fields.Many2one('advanced.timesheet', string='Timesheet', required=True, readonly=True)
    reason = fields.Text(string='What needs changing', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.timesheet_id._do_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}

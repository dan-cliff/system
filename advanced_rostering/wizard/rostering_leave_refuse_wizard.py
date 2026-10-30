# -*- coding: utf-8 -*-
from odoo import fields, models


class RosteringLeaveRefuseWizard(models.TransientModel):
    _name = 'rostering.leave.refuse.wizard'
    _description = 'Refuse Leave Request'

    leave_id = fields.Many2one('rostering.leave', string='Leave Request', required=True, ondelete='cascade')
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        self.leave_id._do_refuse(self.reason)
        return {'type': 'ir.actions.act_window_close'}

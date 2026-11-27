# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchasingRejectWizard(models.TransientModel):
    _name = 'advanced.purchasing.reject.wizard'
    _description = 'Send Purchase Orders Back'

    order_ids = fields.Many2many('purchase.order', string='Orders', required=True)
    reason = fields.Text('Reason', required=True)

    def action_send_back(self):
        self.ensure_one()
        self.order_ids._purchasing_send_back(self.reason)
        return {'type': 'ir.actions.act_window_close'}

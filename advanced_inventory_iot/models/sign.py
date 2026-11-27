# -*- coding: utf-8 -*-
from odoo import fields, models

from .iot_node import ROLE_SIGN


class AdvancedInventorySign(models.Model):
    _inherit = 'advanced.inventory.sign'

    node_ids = fields.One2many('iot.node', 'inventory_sign_id', string='Screens (Nodes)')
    node_count = fields.Integer(compute='_compute_node_count', string='Screens')

    def _compute_node_count(self):
        for sign in self:
            sign.node_count = len(sign.node_ids)

    def action_view_nodes(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_inventory_iot.action_inventory_sign_nodes')
        action['domain'] = [('role', '=', ROLE_SIGN), ('inventory_sign_id', '=', self.id)]
        action['context'] = {'default_role': ROLE_SIGN, 'default_inventory_sign_id': self.id}
        return action

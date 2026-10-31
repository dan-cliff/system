# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    inventory_received_line_ids = fields.One2many(
        'stock.move.line', compute='_compute_inventory_received', string='Received into Inventory',
        help='What has been received into stock from this order, and where it went.')
    inventory_received_count = fields.Integer(compute='_compute_inventory_received', string='Received Lines')
    inventory_putaway_count = fields.Integer(
        compute='_compute_inventory_received', string='To Put Away',
        help='Lines of ready receipts still to be received and put away.')

    @api.depends('picking_ids.state', 'picking_ids.move_line_ids.quantity', 'picking_ids.move_line_ids.picked')
    def _compute_inventory_received(self):
        for order in self:
            receipts = order.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
            done = receipts.filtered(lambda p: p.state == 'done').move_line_ids
            order.inventory_received_line_ids = done.sorted(lambda l: (l.date or fields.Datetime.now(), l.id), reverse=True)
            order.inventory_received_count = len(done)
            order.inventory_putaway_count = len(receipts.filtered(lambda p: p.state == 'assigned').move_line_ids)

    def action_view_inventory_received(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Received into Inventory: %s', self.name),
            'res_model': 'stock.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('advanced_inventory_purchasing.view_move_line_received_list').id, 'list')],
            'domain': [('id', 'in', self.inventory_received_line_ids.ids)],
            'context': {'create': False},
        }

    def action_print_putaway_list(self):
        self.ensure_one()
        receipts = self.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming' and p.state == 'assigned')
        if not receipts:
            raise UserError(_('This order has no receipt ready to put away.'))
        return receipts.action_print_walk_list()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    inventory_putaway_location_id = fields.Many2one(
        'stock.location', string='Put Away To', compute='_compute_inventory_putaway_location',
        help='Where receipts put this product away: its main storage slot in the receiving warehouse.')
    inventory_received_location_ids = fields.Many2many(
        'stock.location', string='Received To', compute='_compute_inventory_putaway_location',
        help='The locations the received quantities went to.')

    @api.depends('product_id', 'order_id.picking_type_id', 'move_ids.state')
    def _compute_inventory_putaway_location(self):
        for line in self:
            destination = line.order_id.picking_type_id.default_location_dest_id
            if line.product_id.is_storable and destination:
                line.inventory_putaway_location_id = destination._get_putaway_strategy(line.product_id)
            else:
                line.inventory_putaway_location_id = False
            done = line.move_ids.filtered(lambda m: m.state == 'done').move_line_ids
            line.inventory_received_location_ids = done.location_dest_id

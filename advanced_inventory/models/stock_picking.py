# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    walk_kind = fields.Selection(
        [('pick', 'Pick'), ('putaway', 'Put Away')], compute='_compute_walk_kind',
        help='Pick: products are taken from storage. Put Away: products go into storage.')

    @api.depends('picking_type_code', 'location_dest_id.usage', 'location_id.usage')
    def _compute_walk_kind(self):
        for picking in self:
            picking.walk_kind = 'putaway' if picking.picking_type_code == 'incoming' or (
                picking.location_id.usage != 'internal' and picking.location_dest_id.usage == 'internal') or (
                picking.location_dest_id.storage_level and not picking.location_id.storage_level) else 'pick'

    def button_validate(self):
        user = self.env.user
        if (not self.env.su and user.has_group('advanced_inventory.group_inventory_user')
                and not user.has_group('advanced_inventory.group_transfer_validate')):
            raise UserError(_('Validating transfers needs the "Transfers: Validate" permission.'))
        return super().button_validate()

    def action_print_walk_list(self):
        return self.env.ref('advanced_inventory.action_report_walk_list').report_action(self)

    # ── Walk screens (Scanner app, pick and put-away lists) ───────────────

    def inventory_walk_lines(self):
        """The transfers' detailed operations in walk order, for the scanner's
        pick and put-away screens."""
        lines = self.move_line_ids.sorted(lambda l: (l.walk_sequence, l.picking_id.id, l.id))
        return [{
            'id': line.id,
            'picking': line.picking_id.name,
            'product_id': line.product_id.id,
            'product': line.product_id.display_name,
            'product_barcode': line.product_id.barcode or '',
            'default_code': line.product_id.default_code or '',
            'lot': line.lot_id.name or line.lot_name or '',
            'tracking': line.product_id.tracking,
            'location': line.walk_location_id.display_name,
            'location_code': line.walk_location_id.layout_code or line.walk_location_id.name,
            'location_barcode': line.walk_location_id.barcode or '',
            'from': line.location_id.display_name,
            'to': line.location_dest_id.display_name,
            'walk': line.walk_sequence,
            'qty': line.quantity,
            'picked': line.picked,
            'uom': line.product_uom_id.name,
        } for line in lines]

    def inventory_walk_set_qty(self, line_id, qty):
        line = self.move_line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError(_('This line is not on the transfer any more.'))
        line.write({'quantity': max(float(qty), 0.0), 'picked': True})
        return True

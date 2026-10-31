# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AdvancedInventoryProductSlot(models.Model):
    """Where a product is kept: a shelf or tote of the warehouse layout.

    A product's main slot in a warehouse gets a put-away rule, so receipts
    into that warehouse put it there; picking then finds it there, and both
    follow the walk order."""
    _name = 'advanced.inventory.product.slot'
    _description = 'Product Storage Slot'
    _order = 'walk_sequence, sequence, id'

    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='cascade', index=True)
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True, index=True)
    location_id = fields.Many2one(
        'stock.location', string='Location', required=True, ondelete='cascade', index=True,
        domain="[('usage', '=', 'internal'), ('storage_level', 'in', ('shelf', 'tote'))]")
    warehouse_id = fields.Many2one(related='location_id.warehouse_id', store=True, string='Warehouse')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, default=lambda self: self.env.company)
    sequence = fields.Integer(default=10)
    is_primary = fields.Boolean(
        string='Main Slot', default=True,
        help='Receipts into this warehouse put the product here. One main slot per product and warehouse.')
    min_qty = fields.Float(string='Min', digits='Product Unit', help='Refill the slot below this quantity.')
    max_qty = fields.Float(string='Capacity', digits='Product Unit', help='How much fits in the slot.')
    qty_on_hand = fields.Float(string='In Slot', compute='_compute_qty_on_hand', digits='Product Unit')
    needs_refill = fields.Boolean(compute='_compute_qty_on_hand')
    walk_sequence = fields.Integer(related='location_id.walk_sequence', store=True, string='Walk Order')
    putaway_rule_id = fields.Many2one('stock.putaway.rule', string='Put-away Rule', readonly=True, copy=False)

    _product_location_uniq = models.Constraint(
        'UNIQUE(product_id, location_id)', 'The product already has this slot.')

    def _compute_qty_on_hand(self):
        groups = self.env['stock.quant']._read_group(
            [('product_id', 'in', self.product_id.ids), ('location_id', 'child_of', self.location_id.ids)],
            ['product_id', 'location_id'], ['quantity:sum'])
        quantities = {}
        for product, location, qty in groups:
            for slot in self.filtered(lambda s: s.product_id == product):
                if location.parent_path.startswith(slot.location_id.parent_path):
                    quantities[slot.id] = quantities.get(slot.id, 0.0) + qty
        for slot in self:
            slot.qty_on_hand = quantities.get(slot.id, 0.0)
            slot.needs_refill = bool(slot.min_qty) and slot.qty_on_hand < slot.min_qty

    @api.constrains('product_id', 'warehouse_id', 'is_primary')
    def _check_one_primary(self):
        for slot in self.filtered('is_primary'):
            if self.search_count([('product_id', '=', slot.product_id.id), ('warehouse_id', '=', slot.warehouse_id.id),
                                  ('is_primary', '=', True), ('id', '!=', slot.id)]):
                raise ValidationError(_('%(product)s already has a main slot in %(warehouse)s.',
                                        product=slot.product_id.display_name, warehouse=slot.warehouse_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        slots._sync_putaway_rule()
        return slots

    def write(self, vals):
        res = super().write(vals)
        if {'product_id', 'location_id', 'is_primary', 'company_id'} & set(vals):
            self._sync_putaway_rule()
        return res

    def unlink(self):
        rules = self.sudo().putaway_rule_id
        res = super().unlink()
        rules.unlink()
        return res

    def _sync_putaway_rule(self):
        Rule = self.env['stock.putaway.rule'].sudo()
        for slot in self.sudo():
            warehouse = slot.location_id.warehouse_id
            if not slot.is_primary or not warehouse:
                slot.putaway_rule_id.unlink()
                continue
            vals = {
                'product_id': slot.product_id.id,
                'location_in_id': warehouse.lot_stock_id.id,
                'location_out_id': slot.location_id.id,
                'company_id': slot.location_id.company_id.id or slot.company_id.id,
                'sequence': 5,
            }
            if slot.putaway_rule_id:
                slot.putaway_rule_id.write(vals)
            else:
                slot.putaway_rule_id = Rule.create(vals)

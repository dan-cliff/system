# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

# The levels of the warehouse layout, from the biggest to the smallest. Code
# (the layout designer, labels, signs and walk order) depends on these, so
# they are a fixed selection rather than an option list.
STORAGE_LEVELS = [
    ('room', 'Room'),
    ('aisle', 'Aisle'),
    ('shelf', 'Shelf'),
    ('tote', 'Tote'),
]
LEVEL_RANK = {level: rank for rank, (level, _label) in enumerate(STORAGE_LEVELS)}
LEVEL_PREFIX = {'room': 'R', 'aisle': 'A', 'shelf': 'S', 'tote': 'T'}


class StockLocation(models.Model):
    _inherit = 'stock.location'
    # Locations list in walk order, so every picker of locations follows the route.
    _order = 'walk_sequence, complete_name, id'

    storage_level = fields.Selection(
        STORAGE_LEVELS, string='Layout Level', index=True,
        help='Where this location sits in the warehouse layout: a room, an aisle in it, '
             'a shelf in the aisle or a tote on the shelf.')
    layout_code = fields.Char(
        string='Layout Code', size=12,
        help='Short code shown on the floor plan, labels and signs, e.g. A3 for aisle 3. '
             'Also builds the barcode of new locations.')
    layout_x = fields.Float(string='X (m)', digits=(16, 2))
    layout_y = fields.Float(string='Y (m)', digits=(16, 2))
    layout_w = fields.Float(string='Width (m)', digits=(16, 2), default=2.0)
    layout_h = fields.Float(string='Depth (m)', digits=(16, 2), default=1.0)
    layout_color = fields.Char(string='Colour')
    layout_sequence = fields.Integer(
        string='Order', default=10,
        help='Order among the locations with the same parent; the walk order follows it.')
    walk_sequence = fields.Integer(
        string='Walk Order', index=True, default=0, copy=False,
        help='Position of this location on the route through the warehouse. Picking and '
             'put-away both follow it. Numbered by the layout designer (Number Walk Order).')
    product_slot_ids = fields.One2many('advanced.inventory.product.slot', 'location_id', string='Assigned Products')
    inventory_product_count = fields.Integer(string='Products Stored', compute='_compute_inventory_contents')
    inventory_qty = fields.Float(string='Units Stored', compute='_compute_inventory_contents', digits='Product Unit')

    def _compute_inventory_contents(self):
        groups = self.env['stock.quant']._read_group(
            [('location_id', 'child_of', self.ids), ('quantity', '>', 0)],
            ['location_id'], ['product_id:count_distinct', 'quantity:sum'])
        by_location = {location: (count, qty) for location, count, qty in groups}
        for location in self:
            count = qty = 0
            for child, (child_count, child_qty) in by_location.items():
                if child.parent_path.startswith(location.parent_path):
                    count += child_count
                    qty += child_qty
            location.inventory_product_count = count
            location.inventory_qty = qty

    # ── Barcodes ──────────────────────────────────────────────────────────

    def _inventory_barcode_base(self):
        """WH-R1-A2-S3-T4: the warehouse code and each layout level's code."""
        self.ensure_one()
        parts = []
        location = self
        while location and location.storage_level:
            code = location.layout_code or '%s%s' % (LEVEL_PREFIX[location.storage_level], location.id or '')
            parts.append(re.sub(r'[^A-Za-z0-9]+', '', code).upper() or LEVEL_PREFIX[location.storage_level])
            location = location.location_id
        warehouse = self.warehouse_id
        if warehouse:
            parts.append(re.sub(r'[^A-Za-z0-9]+', '', warehouse.code or '').upper() or 'WH')
        return '-'.join(reversed(parts))

    def _inventory_assign_barcodes(self):
        """Give layout locations without a barcode one built from the layout codes."""
        for location in self.filtered(lambda l: l.storage_level and not l.barcode):
            base = location._inventory_barcode_base()
            barcode, index = base, 1
            while self.with_context(active_test=False).search_count([
                    ('barcode', '=', barcode), ('company_id', '=', location.company_id.id), ('id', '!=', location.id)]):
                index += 1
                barcode = '%s-%s' % (base, index)
            location.barcode = barcode

    @api.model_create_multi
    def create(self, vals_list):
        locations = super().create(vals_list)
        locations._inventory_assign_barcodes()
        return locations

    def write(self, vals):
        if 'storage_level' in vals or 'location_id' in vals:
            self._inventory_check_level(vals)
        res = super().write(vals)
        if vals.get('storage_level'):
            self._inventory_assign_barcodes()
        return res

    def _inventory_check_level(self, vals):
        for location in self:
            level = vals.get('storage_level', location.storage_level)
            parent = self.browse(vals['location_id']) if vals.get('location_id') else location.location_id
            if level and parent.storage_level and LEVEL_RANK[parent.storage_level] >= LEVEL_RANK[level]:
                levels = dict(STORAGE_LEVELS)
                raise UserError(self.env._(
                    'A %(level)s can\'t sit inside a %(parent)s: rooms hold aisles, aisles hold shelves '
                    'and shelves hold totes.', level=levels[level].lower(), parent=levels[parent.storage_level].lower()))

    # ── Actions ───────────────────────────────────────────────────────────

    def action_open_layout_designer(self):
        self.ensure_one()
        if not self.warehouse_id:
            raise UserError(self.env._('%s is not in a warehouse.', self.display_name))
        return self.warehouse_id.action_open_layout_designer(select_location_id=self.id)

    def action_print_layout_label(self):
        """Print the locations' labels with the first label design for their level."""
        levels = set(self.mapped('storage_level'))
        if len(levels) != 1 or not next(iter(levels)):
            raise UserError(self.env._('Pick rooms, aisles, shelves or totes of one kind to print their labels.'))
        level = next(iter(levels))
        company = self[:1].company_id or self.env.company
        template = self.env['advanced.inventory.label.template'].search([
            ('target', '=', level), '|', ('company_id', '=', False), ('company_id', '=', company.id)], limit=1)
        if not template:
            raise UserError(self.env._(
                'There is no label design for %s yet. Add one in Configuration › Labels & Signage › Label Designs.',
                dict(STORAGE_LEVELS)[level].lower()))
        return template.report_action_id.report_action(self, config=False)

    def action_view_inventory_contents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Stock in %s', self.display_name),
            'res_model': 'stock.quant',
            'view_mode': 'list',
            'domain': [('location_id', 'child_of', self.id), ('quantity', '!=', 0)],
            'context': {'create': False},
        }

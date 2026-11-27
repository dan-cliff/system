# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .stock_location import LEVEL_PREFIX, LEVEL_RANK, STORAGE_LEVELS

COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')
# Default colours of each level on the floor plan (house palette).
LEVEL_COLORS = {'room': '#F2F2FA', 'aisle': '#A9ABDC', 'shelf': '#3BB8FF', 'tote': '#FFC93C'}
# Default sizes (metres) of a new location on the floor plan.
LEVEL_SIZES = {'room': (12.0, 8.0), 'aisle': (1.5, 8.0), 'shelf': (1.2, 0.6), 'tote': (0.4, 0.3)}


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    inventory_barcode = fields.Char(
        string='Barcode', copy=False,
        help='Printed on the warehouse label and read by the Scanner app. Defaults to WH- and the short name.')
    layout_floor_width = fields.Float(string='Floor Width (m)', default=40.0, digits=(16, 1))
    layout_floor_depth = fields.Float(string='Floor Depth (m)', default=25.0, digits=(16, 1))
    layout_location_count = fields.Integer(string='Layout Locations', compute='_compute_layout_location_count')

    _inventory_barcode_uniq = models.Constraint(
        'UNIQUE(inventory_barcode, company_id)', 'The warehouse barcode must be unique per company.')

    @api.constrains('layout_floor_width', 'layout_floor_depth')
    def _check_layout_floor(self):
        for warehouse in self:
            if not (1 <= warehouse.layout_floor_width <= 2000 and 1 <= warehouse.layout_floor_depth <= 2000):
                raise ValidationError(self.env._('The floor plan must be between 1 and 2000 metres on each side.'))

    def _compute_layout_location_count(self):
        for warehouse in self:
            warehouse.layout_location_count = self.env['stock.location'].search_count([
                ('location_id', 'child_of', warehouse.lot_stock_id.id), ('storage_level', '!=', False)])

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        for warehouse in warehouses.filtered(lambda w: not w.inventory_barcode):
            warehouse.inventory_barcode = 'WH-%s' % re.sub(r'[^A-Za-z0-9]+', '', warehouse.code or str(warehouse.id)).upper()
        return warehouses

    # ── Layout designer ───────────────────────────────────────────────────

    def action_open_layout_designer(self, select_location_id=False):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'advanced_inventory.layout_designer',
            'name': self.env._('Layout: %s', self.name),
            'params': {'warehouse_id': self.id, 'select_location_id': select_location_id or False},
        }

    def _layout_locations(self):
        self.ensure_one()
        return self.env['stock.location'].search([
            ('location_id', 'child_of', self.lot_stock_id.id), ('storage_level', '!=', False)])

    @api.model
    def layout_designer_load(self, warehouse_id):
        """Everything the layout designer draws: the floor and every layout location.
        Without a warehouse (the designer reopened after a reload), the company's first."""
        warehouse = self.browse(warehouse_id).exists() if warehouse_id else self.search(
            [('company_id', '=', self.env.company.id)], limit=1)
        if not warehouse:
            raise UserError(self.env._('This warehouse no longer exists.'))
        locations = warehouse._layout_locations()
        quants = self.env['stock.quant']._read_group(
            [('location_id', 'in', locations.ids), ('quantity', '>', 0)],
            ['location_id', 'product_id'], ['quantity:sum'])
        contents = {}
        for location, product, qty in quants:
            contents.setdefault(location.id, []).append([product.display_name, qty])
        slots = {}
        for slot in self.env['advanced.inventory.product.slot'].search([('location_id', 'in', locations.ids)]):
            slots.setdefault(slot.location_id.id, []).append(slot.product_id.display_name)
        root = warehouse.lot_stock_id
        return {
            'warehouse': {
                'id': warehouse.id,
                'name': warehouse.name,
                'code': warehouse.code,
                'barcode': warehouse.inventory_barcode or '',
                'floor_width': warehouse.layout_floor_width,
                'floor_depth': warehouse.layout_floor_depth,
                'root_id': root.id,
                'root_name': root.display_name,
            },
            'levels': [{'key': key, 'label': label, 'color': LEVEL_COLORS[key], 'size': LEVEL_SIZES[key],
                        'prefix': LEVEL_PREFIX[key]} for key, label in STORAGE_LEVELS],
            'nodes': [{
                'id': location.id,
                'parent_id': location.location_id.id if location.location_id != root else False,
                'name': location.name,
                'level': location.storage_level,
                'code': location.layout_code or '',
                'barcode': location.barcode or '',
                'x': location.layout_x,
                'y': location.layout_y,
                'w': location.layout_w,
                'h': location.layout_h,
                'color': location.layout_color or '',
                'sequence': location.layout_sequence,
                'walk': location.walk_sequence,
                'contents': sorted(contents.get(location.id, []), key=lambda c: -c[1])[:25],
                'slots': slots.get(location.id, [])[:25],
            } for location in locations],
        }

    @api.model
    def layout_designer_save(self, warehouse_id, nodes, deleted_ids=None, number_walk=False):
        """Create, update and archive the layout's locations from the designer.

        ``nodes``: [{id (int, or a 'new_...' string for new ones), parent_id
        (id, 'new_...' or False for the warehouse's stock location), name, level,
        code, barcode, x, y, w, h, color, sequence}]."""
        warehouse = self.browse(warehouse_id).exists()
        if not warehouse:
            raise UserError(self.env._('This warehouse no longer exists.'))
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._('Only Inventory administrators can change the warehouse layout.'))
        Location = self.env['stock.location']
        existing = warehouse._layout_locations()
        root = warehouse.lot_stock_id
        warehouse._layout_enable_locations()

        nodes = [node for node in nodes or [] if isinstance(node, dict) and node.get('level') in LEVEL_RANK]
        ids = {}  # designer id -> stock.location
        for node in nodes:
            if isinstance(node.get('id'), int):
                location = existing.filtered(lambda l, i=node['id']: l.id == i)
                if not location:
                    raise UserError(self.env._('A location in the layout is not in %s any more. Reload the designer.',
                                               warehouse.name))
                ids[node['id']] = location

        def values(node):
            name = (node.get('name') or '').strip()
            if not name:
                raise UserError(self.env._('Every room, aisle, shelf and tote needs a name.'))
            color = node.get('color') or False
            vals = {
                'name': name,
                'storage_level': node['level'],
                'layout_code': (node.get('code') or '').strip()[:12] or False,
                'layout_x': self._layout_number(node.get('x')),
                'layout_y': self._layout_number(node.get('y')),
                'layout_w': max(self._layout_number(node.get('w'), 1.0), 0.05),
                'layout_h': max(self._layout_number(node.get('h'), 1.0), 0.05),
                'layout_color': color if color and COLOR_RE.match(color) else False,
                'layout_sequence': int(self._layout_number(node.get('sequence'), 10)),
            }
            barcode = (node.get('barcode') or '').strip()
            if barcode:
                vals['barcode'] = barcode
            return vals

        # Parents before children, so new children can point at new parents.
        for node in sorted(nodes, key=lambda n: LEVEL_RANK[n['level']]):
            parent_ref = node.get('parent_id')
            parent = ids.get(parent_ref) if parent_ref else root
            if parent_ref and not parent:
                raise UserError(self.env._('"%s" is inside a location that is not in the layout.', node.get('name')))
            vals = dict(values(node), location_id=parent.id)
            if isinstance(node.get('id'), int):
                location = ids[node['id']]
                changed = {}
                for key, value in vals.items():
                    current = location[key].id if key == 'location_id' else location[key]
                    if current != value:
                        changed[key] = value
                if changed:
                    location.write(changed)
            else:
                vals.update(usage='internal', company_id=warehouse.company_id.id)
                ids[node.get('id')] = Location.create(vals)

        kept = Location.browse([location.id for location in ids.values()])
        removed = (existing - kept) | existing.filtered(lambda l: l.id in (deleted_ids or []))
        removed -= kept
        if removed:
            stocked = self.env['stock.quant'].search([
                ('location_id', 'child_of', removed.ids), ('quantity', '!=', 0)], limit=1)
            if stocked:
                raise UserError(self.env._(
                    '%(location)s still holds stock (%(product)s), so it can\'t be removed from the layout. '
                    'Move the stock first.', location=stocked.location_id.display_name,
                    product=stocked.product_id.display_name))
            self.env['advanced.inventory.product.slot'].search([('location_id', 'in', removed.ids)]).unlink()
            removed.write({'active': False})
        if number_walk:
            warehouse._layout_number_walk()
        return self.layout_designer_load(warehouse.id)

    @api.model
    def layout_designer_number_walk(self, warehouse_id):
        warehouse = self.browse(warehouse_id).exists()
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._('Only Inventory administrators can change the warehouse layout.'))
        warehouse._layout_number_walk()
        return self.layout_designer_load(warehouse.id)

    @api.model
    def _layout_number(self, value, default=0.0):
        try:
            return min(max(float(value), -100000.0), 100000.0)
        except (TypeError, ValueError):
            return default

    def _layout_enable_locations(self):
        """A layout is made of storage locations: switch on Inventory's Storage
        Locations feature the first time one is saved."""
        group = self.env.ref('stock.group_stock_multi_locations')
        user_group = self.env.ref('base.group_user')
        if group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [(4, group.id)]})

    def _layout_walk_order(self, locations):
        """The layout locations in the order of the walk through the warehouse.

        Rooms go front to back (then left to right), aisles left to right (then
        front to back). Shelves follow their aisle, snaking: up the first aisle,
        down the next, so the walk never doubles back. Totes follow the order
        they are listed on their shelf."""
        self.ensure_one()
        children = {}
        for location in locations:
            children.setdefault(location.location_id.id, []).append(location)

        ordered = []

        def sort_key(location):
            if location.storage_level == 'tote':
                return (location.layout_sequence, location.id)
            if location.storage_level == 'room':
                return (round(location.layout_y, 2), round(location.layout_x, 2), location.id)
            return (round(location.layout_x, 2), round(location.layout_y, 2), location.id)

        def visit(parent, flip=False):
            kids = children.get(parent.id, [])
            if parent.storage_level == 'aisle':
                vertical = parent.layout_h >= parent.layout_w
                kids = sorted(kids, key=lambda l: (
                    round(l.layout_y if vertical else l.layout_x, 2), l.layout_sequence, l.id), reverse=flip)
            else:
                kids = sorted(kids, key=sort_key)
            aisle_index = 0
            for kid in kids:
                ordered.append(kid)
                if kid.storage_level == 'aisle':
                    visit(kid, flip=bool(aisle_index % 2))
                    aisle_index += 1
                else:
                    visit(kid)

        visit(self.lot_stock_id)
        return ordered

    def _layout_number_walk(self):
        """Number every layout location along the walk (10, 20, 30, ...)."""
        for warehouse in self:
            locations = warehouse._layout_locations()
            ordered = warehouse._layout_walk_order(locations)
            positions = {}
            for index, location in enumerate(ordered, start=1):
                siblings = positions.setdefault(location.location_id.id, [])
                siblings.append(location)
                vals = {}
                if location.walk_sequence != index * 10:
                    vals['walk_sequence'] = index * 10
                if location.layout_sequence != len(siblings) * 10:
                    vals['layout_sequence'] = len(siblings) * 10
                if vals:
                    location.write(vals)
        return True

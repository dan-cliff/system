# -*- coding: utf-8 -*-
"""Manufacture: Pick, Produce and Store.

A route of its own (Inventory › Configuration › Routes), selectable on
products and product categories, independent of the warehouse's own
Manufacture steps setting:

1. Pick Components: the components are picked from the warehouse's stock
   to its Manufacturing Pick Area (one transfer per manufacturing order).
2. Manufacture: the manufacturing order consumes them there and produces
   the new product into the Manufacturing Output area.
3. Store Finished Products: the new product is moved from the output area
   to the warehouse's stock.

It is created once for Cliffs Country Crafts (data/manufacturing_route_data.xml)
and is then an ordinary route: its locations, operation types and rules can
be changed (or the route archived) in Inventory, and upgrades leave it alone.
"""
import logging
import re

from odoo import Command, _, api, fields, models

_logger = logging.getLogger(__name__)

ROUTE_XMLID = 'route_pick_produce_store'
DONE_PARAM = 'advanced_manufacturing.pick_produce_store_route_created'


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    mrp_components_route_id = fields.Many2one(
        'stock.route', string='Pick Components With', check_company=True,
        help='Manufacturing orders of this type get their components picked with this route: each '
             'order gets a transfer bringing its components from stock to where it consumes them.',
    )


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _adjust_procure_method(self, picking_type_code=False):
        result = super()._adjust_procure_method(picking_type_code=picking_type_code)
        for move in self:
            production = move.raw_material_production_id
            route = production.picking_type_id.mrp_components_route_id
            if route and move.location_id == production.location_src_id and move.state in ('draft', 'waiting', 'confirmed'):
                move.route_ids = [Command.link(route.id)]
                move.procure_method = 'make_to_order'
        return result


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model
    def _mrp_find_company(self, name='Cliffs Country Crafts'):
        """The company called (about) this name, ignoring case and apostrophes."""
        wanted = re.sub(r"[^a-z0-9]", '', name.lower())
        for company in self.env['res.company'].sudo().search([]):
            if re.sub(r"[^a-z0-9]", '', (company.name or '').lower()) == wanted:
                return company
        return self.env['res.company']

    @api.model
    def _mrp_ensure_pick_produce_store_route(self, company_name='Cliffs Country Crafts'):
        """Create the route once, for the named company's main warehouse."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(DONE_PARAM):
            return False
        company = self._mrp_find_company(company_name)
        if not company:
            _logger.info('Manufacturing: no company called %s, the Pick, Produce and Store route was not created.',
                         company_name)
            return False
        warehouse = self.sudo().search([('company_id', '=', company.id)], order='sequence, id', limit=1)
        if not warehouse:
            _logger.info('Manufacturing: %s has no warehouse, the Pick, Produce and Store route was not created.',
                         company.name)
            return False
        route = warehouse._mrp_create_pick_produce_store_route()
        self.env['ir.model.data'].sudo().create({
            'module': 'advanced_manufacturing', 'name': ROUTE_XMLID, 'model': 'stock.route',
            'res_id': route.id, 'noupdate': True,
        })
        params.set_param(DONE_PARAM, route.id)
        return route

    def _mrp_create_pick_produce_store_route(self):
        """Create the route, its two areas, three operation types and four rules."""
        self.ensure_one()
        warehouse = self.sudo()
        company = warehouse.company_id
        Location = self.env['stock.location'].sudo()
        PickingType = self.env['stock.picking.type'].sudo()
        code = re.sub(r'\s', '', warehouse.code or '').upper()

        # Multi-step routes and locations, so routes show on products and categories.
        user_group = self.env.ref('base.group_user').sudo()
        for xmlid in ('stock.group_stock_multi_locations', 'stock.group_adv_location'):
            group = self.env.ref(xmlid)
            if group not in user_group.implied_ids:
                user_group.write({'implied_ids': [Command.link(group.id)]})

        def location(name, suffix):
            barcode = code + suffix
            if Location.search_count([('barcode', '=', barcode), ('company_id', '=', company.id)]):
                barcode = False
            return Location.create({
                'name': name, 'usage': 'internal', 'location_id': warehouse.view_location_id.id,
                'company_id': company.id, 'barcode': barcode,
            })

        pick_area = location(_('Manufacturing Pick Area'), 'MFGPICK')
        output_area = location(_('Manufacturing Output'), 'MFGOUT')
        stock = warehouse.lot_stock_id
        production = warehouse._get_production_location()

        def picking_type(name, kind, sequence_code, source, destination, **extra):
            return PickingType.create({
                'name': name, 'code': kind, 'sequence_code': sequence_code, 'warehouse_id': warehouse.id,
                'company_id': company.id, 'default_location_src_id': source.id,
                'default_location_dest_id': destination.id, 'sequence': 20, **extra,
            })

        pick_type = picking_type(_('Pick Components'), 'internal', 'PCM', stock, pick_area)
        manufacture_type = picking_type(_('Manufacturing (Pick, Produce and Store)'), 'mrp_operation', 'MOS',
                                        pick_area, output_area)
        store_type = picking_type(_('Store Finished Products'), 'internal', 'SFP', output_area, stock)

        route = self.env['stock.route'].sudo().create({
            'name': _('Manufacture: Pick, Produce and Store'),
            'company_id': company.id,
            'product_selectable': True,
            'product_categ_selectable': True,
            'warehouse_selectable': False,
            'sequence': 5,
            'rule_ids': [
                Command.create({
                    'name': _('%(wh)s: Manufacture (Pick, Produce and Store)', wh=warehouse.code),
                    'action': 'manufacture',
                    'picking_type_id': manufacture_type.id,
                    'location_dest_id': stock.id,
                    'procure_method': 'make_to_order',
                    'company_id': company.id,
                    'warehouse_id': warehouse.id,
                    'sequence': 10,
                }),
                Command.create({
                    'name': _('%(wh)s: Pick Components', wh=warehouse.code),
                    'action': 'pull',
                    'picking_type_id': pick_type.id,
                    'location_src_id': stock.id,
                    'location_dest_id': pick_area.id,
                    'procure_method': 'make_to_stock',
                    'company_id': company.id,
                    'warehouse_id': warehouse.id,
                    'sequence': 20,
                }),
                Command.create({
                    'name': _('%(wh)s: Consume Components', wh=warehouse.code),
                    'action': 'pull',
                    'picking_type_id': manufacture_type.id,
                    'location_src_id': pick_area.id,
                    'location_dest_id': production.id,
                    'procure_method': 'make_to_order',
                    'company_id': company.id,
                    'warehouse_id': warehouse.id,
                    'sequence': 30,
                }),
                Command.create({
                    'name': _('%(wh)s: Store Finished Products', wh=warehouse.code),
                    'action': 'push',
                    'auto': 'manual',
                    'picking_type_id': store_type.id,
                    'location_src_id': output_area.id,
                    'location_dest_id': stock.id,
                    'company_id': company.id,
                    'warehouse_id': warehouse.id,
                    'sequence': 40,
                }),
            ],
        })
        manufacture_type.mrp_components_route_id = route
        return route

# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models
from odoo.tools import formatLang


class AdvancedInventoryOverview(models.AbstractModel):
    """Figures for the Overview screen and barcode lookups for the Scanner app."""
    _name = 'advanced.inventory.overview'
    _description = 'Inventory Overview'

    @api.model
    def get_overview_data(self):
        company = self.env.company
        currency = company.currency_id
        now = fields.Datetime.now()
        Picking = self.env['stock.picking']
        open_states = ['assigned', 'waiting', 'confirmed']

        operations = []
        types = self.env['stock.picking.type'].search([
            ('code', 'in', ('incoming', 'outgoing', 'internal')), ('company_id', '=', company.id)])
        counts = {}
        for type_, state, count in Picking._read_group(
                [('picking_type_id', 'in', types.ids), ('state', 'in', open_states)],
                ['picking_type_id', 'state'], ['__count']):
            counts.setdefault(type_.id, {}).setdefault(state, 0)
            counts[type_.id][state] += count
        late = dict(Picking._read_group(
            [('picking_type_id', 'in', types.ids), ('state', 'in', open_states), ('scheduled_date', '<', now)],
            ['picking_type_id'], ['__count']))
        for type_ in types:
            by_state = counts.get(type_.id, {})
            ready = by_state.get('assigned', 0)
            waiting = by_state.get('waiting', 0) + by_state.get('confirmed', 0)
            late_count = late.get(type_, 0)
            if not (ready or waiting or late_count) and type_.code == 'internal':
                continue
            operations.append({
                'id': type_.id,
                'name': type_.name,
                'warehouse': type_.warehouse_id.name or '',
                'code': type_.code,
                'kind': 'putaway' if type_.code == 'incoming' else 'pick',
                'ready': ready,
                'waiting': waiting,
                'late': late_count,
            })

        # Stock value at cost, and what it would sell for.
        quants = self.env['stock.quant']._read_group(
            [('location_id.usage', '=', 'internal'), ('company_id', '=', company.id), ('quantity', '>', 0)],
            ['product_id'], ['quantity:sum'])
        value = revenue = 0.0
        negative = self.env['stock.quant'].search_count([
            ('location_id.usage', '=', 'internal'), ('company_id', '=', company.id), ('quantity', '<', 0)])
        for product, qty in quants:
            template = product.product_tmpl_id
            value += qty * product.standard_price
            revenue += qty * (template.cost_analysis_id.sell_price or product.lst_price)

        analyses = self.env['product.cost.analysis'].search([('company_id', 'in', [company.id, False])])
        costed = self.env['product.template'].search_count([('cost_from_analysis', '=', True)])
        refill = self.env['advanced.inventory.product.slot'].search([('company_id', '=', company.id)]).filtered(
            'needs_refill')
        today = datetime.combine(fields.Date.context_today(self), time.min)
        received_today = Picking.search_count([
            ('picking_type_code', '=', 'incoming'), ('state', '=', 'done'), ('date_done', '>=', today),
            ('company_id', '=', company.id)])
        to_pick = self.env['stock.move.line'].search_count([
            ('picking_id.state', '=', 'assigned'), ('picking_code', 'in', ('outgoing', 'internal')),
            ('picked', '=', False), ('company_id', '=', company.id)])
        to_put_away = self.env['stock.move.line'].search_count([
            ('picking_id.state', '=', 'assigned'), ('picking_code', '=', 'incoming'),
            ('picked', '=', False), ('company_id', '=', company.id)])

        def money(amount):
            return formatLang(self.env, amount, currency_obj=currency)

        return {
            'operations': operations,
            'kpis': {
                'stock_value': money(value),
                'potential_revenue': money(revenue),
                'potential_margin': money(revenue - value),
                'margin_percent': round((revenue - value) / revenue * 100, 1) if revenue else 0.0,
                'received_today': received_today,
                'to_pick': to_pick,
                'to_put_away': to_put_away,
                'negative': negative,
                'refill': len(refill),
                'analyses': len(analyses),
                'not_viable': len(analyses.filtered(lambda a: not a.is_viable)),
                'outdated': sum(analyses.mapped('outdated_line_count')),
                'costed': costed,
            },
            'warehouses': [{
                'id': warehouse.id,
                'name': warehouse.name,
                'locations': warehouse.layout_location_count,
            } for warehouse in self.env['stock.warehouse'].search([('company_id', '=', company.id)])],
            'is_manager': self.env.user.has_group('stock.group_stock_manager'),
        }

    @api.model
    def scanner_lookup(self, barcode):
        """What a scanned label is: a product, a location, a warehouse or a transfer."""
        barcode = (barcode or '').strip()
        if not barcode:
            return {'type': False}
        product = self.env['product.product'].search(
            ['|', ('barcode', '=', barcode), ('default_code', '=', barcode)], limit=1)
        if product:
            groups = self.env['stock.quant']._read_group(
                [('product_id', '=', product.id), ('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)],
                ['location_id'], ['quantity:sum'])
            groups.sort(key=lambda g: (g[0].walk_sequence, g[0].complete_name or ''))
            return {
                'type': 'product',
                'id': product.id,
                'name': product.display_name,
                'uom': product.uom_id.name,
                'on_hand': product.qty_available,
                'forecast': product.virtual_available,
                'rows': [[location.display_name, qty] for location, qty in groups],
                'slots': [[slot.location_id.display_name, slot.is_primary, slot.qty_on_hand]
                          for slot in product.product_slot_ids],
            }
        location = self.env['stock.location'].search([('barcode', '=', barcode)], limit=1)
        if location:
            groups = self.env['stock.quant']._read_group(
                [('location_id', 'child_of', location.id), ('quantity', '!=', 0)],
                ['product_id'], ['quantity:sum'])
            groups.sort(key=lambda g: -g[1])
            return {
                'type': 'location',
                'id': location.id,
                'name': location.display_name,
                'level': location.storage_level or '',
                'walk': location.walk_sequence,
                'rows': [[product.display_name, qty] for product, qty in groups],
                'slots': [[slot.product_id.display_name, slot.is_primary, slot.qty_on_hand]
                          for slot in location.product_slot_ids],
            }
        warehouse = self.env['stock.warehouse'].search(
            ['|', ('inventory_barcode', '=', barcode), ('code', '=', barcode)], limit=1)
        if warehouse:
            return {'type': 'warehouse', 'id': warehouse.id, 'name': warehouse.name,
                    'rows': [], 'slots': []}
        picking = self.env['stock.picking'].search([('name', '=', barcode)], limit=1)
        if picking:
            return {'type': 'picking', 'id': picking.id, 'name': picking.name, 'state': picking.state,
                    'walk_kind': picking.walk_kind, 'rows': [], 'slots': []}
        return {'type': False}

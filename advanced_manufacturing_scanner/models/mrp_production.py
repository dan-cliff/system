# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

OPEN_STATES = ('confirmed', 'progress', 'to_close')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # ── Picker ─────────────────────────────────────────────────────────────
    @api.model
    def _scanner_orders_domain(self):
        domain = [('state', 'in', OPEN_STATES), ('company_id', 'in', self.env.companies.ids)]
        if self.env.company.mrp_scanner_ready_only:
            domain += ['|', ('state', 'in', ('progress', 'to_close')), ('reservation_state', '=', 'assigned')]
        return domain

    @api.model
    def scanner_mrp_orders(self):
        """Manufacturing orders for the Scanner's Manufacture picker."""
        orders = self.search(self._scanner_orders_domain(), order='priority desc, date_start, id', limit=200)
        now = fields.Datetime.now()
        return [{
            'id': order.id,
            'name': order.name,
            'product': order.product_id.display_name,
            'qty': order.product_qty,
            'uom': order.product_uom_id.name,
            'state': dict(order._fields['state']._description_selection(self.env)).get(order.state),
            'ready': order.reservation_state == 'assigned',
            'scheduled': fields.Datetime.context_timestamp(order, order.date_start).strftime('%d/%m/%Y %H:%M')
            if order.date_start else '',
            'late': bool(order.date_deadline and order.date_deadline < now),
        } for order in orders]

    @api.model
    def scanner_find_mrp_order(self, name):
        """An open manufacturing order by its scanned reference."""
        order = self.search([('name', '=', (name or '').strip()), ('state', 'in', OPEN_STATES)], limit=1)
        return order.id or False

    # ── One order ──────────────────────────────────────────────────────────
    def _scanner_components(self):
        self.ensure_one()
        return self.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel'))

    def scanner_mrp_data(self):
        self.ensure_one()
        producing = self.qty_producing or self.product_qty - self.qty_produced
        components = []
        for move in self._scanner_components():
            needed = move.should_consume_qty if self.qty_producing else move.product_uom.round(
                move.product_uom_qty * (producing / (self.product_qty or 1)))
            components.append({
                'id': move.id,
                'product': move.product_id.display_name,
                'barcode': move.product_id.barcode or '',
                'default_code': move.product_id.default_code or '',
                'needed': needed,
                'done': move.quantity if move.picked else 0.0,
                'uom': move.product_uom.name,
                'available': move.state == 'assigned',
            })
        return {
            'id': self.id,
            'name': self.name,
            'product': self.product_id.display_name,
            'product_barcode': self.product_id.barcode or '',
            'qty': self.product_qty,
            'qty_producing': producing,
            'uom': self.product_uom_id.name,
            'tracking': self.product_tracking,
            'lot': ', '.join(self.lot_producing_ids.mapped('name')),
            'state': self.state,
            'components': components,
            'require_components': self.company_id.mrp_scanner_require_components,
        }

    def scanner_mrp_set_producing(self, qty):
        """The quantity being produced now (components to consume follow it)."""
        self.ensure_one()
        qty = float(qty or 0)
        if qty <= 0:
            raise UserError(_('The quantity to produce must be more than 0.'))
        self.qty_producing = qty
        self._set_qty_producing(False)
        return self.scanner_mrp_data()

    def scanner_mrp_set_component(self, move_id, qty):
        """Record how much of a component was used (scanned or typed)."""
        self.ensure_one()
        move = self._scanner_components().filtered(lambda m: m.id == move_id)
        if not move:
            raise UserError(_('That component is no longer on %s.', self.name))
        qty = float(qty or 0)
        if qty < 0:
            raise UserError(_('The quantity cannot be negative.'))
        move.quantity = qty
        move.picked = True
        return self.scanner_mrp_data()

    def scanner_mrp_set_lot(self, lot_name):
        """The lot / serial number produced, found or created (empty: numbered automatically)."""
        self.ensure_one()
        if self.product_tracking == 'none':
            return self.scanner_mrp_data()
        lot_name = (lot_name or '').strip()
        if not lot_name:
            if not self.lot_producing_ids:
                if self.product_tracking == 'serial' and self.product_qty != 1:
                    raise UserError(_('Assign serial numbers for several units in Odoo.'))
                self.lot_producing_ids = [Command.create(self._prepare_stock_lot_values())]
            return self.scanner_mrp_data()
        if self.product_tracking == 'serial' and self.product_qty != 1:
            raise UserError(_('Assign serial numbers for several units in Odoo.'))
        Lot = self.env['stock.lot']
        lot = Lot.search([
            ('product_id', '=', self.product_id.id), ('name', '=', lot_name),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=1) or Lot.create({'product_id': self.product_id.id, 'name': lot_name,
                                   'company_id': self.company_id.id})
        self.lot_producing_ids = [Command.set(lot.ids)]
        return self.scanner_mrp_data()

    def scanner_mrp_produce(self):
        """Produce the order. Returns {'done': True} or an Odoo action to finish in a dialog."""
        self.ensure_one()
        if self.state not in OPEN_STATES:
            raise UserError(_('%s is not open any more.', self.name))
        if self.company_id.mrp_scanner_require_components:
            missing = self._scanner_components().filtered(lambda m: not m.picked)
            if missing:
                raise UserError(_('Scan every component first: %s.',
                                  ', '.join(missing.product_id.mapped('display_name'))))
        if self.product_tracking in ('lot', 'serial') and not self.lot_producing_ids:
            self.scanner_mrp_set_lot('')
        if not self.qty_producing:
            self.qty_producing = self.product_qty - self.qty_produced
            self._set_qty_producing(False)
        partial = self.product_uom_id.compare(self.qty_producing, self.product_qty) < 0
        result = self.with_context(
            skip_redirection=True, skip_backorder=True,
            mo_ids_to_backorder=self.ids if partial else [],
        ).button_mark_done()
        if isinstance(result, dict) and result.get('res_model'):
            return {'done': False, 'action': result}
        return {'done': self.state == 'done', 'name': self.name}

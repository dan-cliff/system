# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .mrp_workcenter import iso_utc


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    terminal_instructions = fields.Html(
        string='Instructions', translate=True, sanitize=True,
        help='Shown to workers on the Work Centre app when they open a work order for this operation.',
    )


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    working_employee_ids = fields.Many2many(
        'hr.employee', string='Working Now', compute='_compute_working_employee_ids',
        help='Workers with a timer running on this work order (from the Work Centre app).',
    )

    @api.depends('time_ids.date_end', 'time_ids.employee_id')
    def _compute_working_employee_ids(self):
        for workorder in self:
            workorder.working_employee_ids = workorder.time_ids.filtered(lambda t: not t.date_end).employee_id

    def _should_start_timer(self):
        # The Work Centre app starts its own timer, for the worker who signed in.
        if self.env.context.get('mrp_terminal_no_timer'):
            return False
        return super()._should_start_timer()

    # ── Work Centre app payload ────────────────────────────────────────────
    def _terminal_payload(self):
        self.ensure_one()
        production = self.production_id
        open_times = self.time_ids.filtered(lambda t: not t.date_end)
        others = production.workorder_ids - self
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'production_id': production.id,
            'production': production.name,
            'priority': production.priority == '1',
            'product_id': self.product_id.id,
            'product': self.product_id.display_name,
            'product_tmpl_id': self.product_id.product_tmpl_id.id,
            'tracking': self.product_id.tracking,
            'lots': [{'id': lot.id, 'name': lot.name} for lot in production.lot_producing_ids],
            'qty_production': production.product_qty,
            'qty_producing': production.qty_producing,
            'qty_remaining': self.qty_remaining,
            'uom': production.product_uom_id.name,
            'date_start': iso_utc(self.date_start),
            'date_deadline': iso_utc(production.date_deadline),
            'duration_expected': self.duration_expected,
            'duration': self.duration,
            'running': [{
                'employee_id': time.employee_id.id,
                'start': iso_utc(time.date_start),
            } for time in open_times if time.employee_id],
            'is_last': all(wo.state in ('done', 'cancel') for wo in others),
            'instructions': self.operation_id.terminal_instructions or '',
            'components': [{
                'product': move.product_id.display_name,
                'qty': move.product_uom_qty,
                'uom': move.product_uom.name,
                'available': move.state == 'assigned' or move.picked,
            } for move in self._terminal_component_moves()],
        }

    def _terminal_component_moves(self):
        """Components to show: the operation's own, and those consumed by no
        particular operation on the order's last work order."""
        self.ensure_one()
        moves = self.move_raw_ids
        others = self.production_id.workorder_ids - self
        if all(wo.state in ('done', 'cancel') for wo in others):
            moves |= self.production_id.move_raw_ids.filtered(lambda m: not m.workorder_id and not m.operation_id)
        return moves.filtered(lambda m: m.state != 'cancel')

    # ── Recording work from the Work Centre app ────────────────────────────
    # Each method gets the worker, the (naive UTC) time they did it and the
    # event from the app, and returns a message for the log (or raises).
    def _terminal_check_open(self):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_('Work order %s is already finished or cancelled.', self.display_name))
        if self.production_id.state in ('done', 'cancel'):
            raise UserError(_('Manufacturing order %s is already done or cancelled.', self.production_id.name))

    def _terminal_open_times(self, employee=None):
        times = self.time_ids.filtered(lambda t: not t.date_end)
        return times.filtered(lambda t: t.employee_id == employee) if employee is not None else times

    def _terminal_start(self, employee, when, event):
        self.ensure_one()
        self._terminal_check_open()
        if self.working_state == 'blocked':
            raise UserError(_('The work centre is blocked. Unblock it before starting work.'))
        if self._terminal_open_times(employee):
            return _('%s was already working on it.', employee.name)
        self.with_context(mrp_terminal_no_timer=True).button_start()
        vals = self._prepare_timeline_vals(self.duration, when)
        vals.update({
            'employee_id': employee.id,
            'user_id': employee.user_id.id or False,
            'description': _('Work Centre app: %s', employee.name),
        })
        self.env['mrp.workcenter.productivity'].create(vals)
        if self.date_start and when < self.date_start:
            self.with_context(bypass_duration_calculation=True).date_start = when
        return _('Started by %s.', employee.name)

    def _terminal_stop_times(self, times, when):
        for time in times:
            time.date_end = max(when, time.date_start)

    def _terminal_pause(self, employee, when, event):
        self.ensure_one()
        times = self._terminal_open_times(employee)
        if not times:
            return _('%s was not working on it.', employee.name)
        self._terminal_stop_times(times, when)
        return _('Paused by %s.', employee.name)

    def _terminal_set_lot(self, lot_name):
        """Set the lot / serial number the order produces, finding or creating it."""
        self.ensure_one()
        production = self.production_id
        tracking = production.product_id.tracking
        if tracking == 'none':
            return
        lot_name = (lot_name or '').strip()
        if not lot_name:
            if production.lot_producing_ids:
                return
            if tracking == 'serial' and production.product_qty != 1:
                return
            lot_name = production._prepare_stock_lot_values()['name']
        if production.lot_producing_ids.filtered(lambda lot: lot.name == lot_name):
            return
        if tracking == 'serial' and production.product_qty != 1:
            raise UserError(_('Serial numbers for several units are assigned in Odoo, not the Work Centre app.'))
        Lot = self.env['stock.lot']
        lot = Lot.search([
            ('product_id', '=', production.product_id.id), ('name', '=', lot_name),
            ('company_id', 'in', [False, production.company_id.id]),
        ], limit=1) or Lot.create({
            'product_id': production.product_id.id, 'name': lot_name, 'company_id': production.company_id.id,
        })
        production.lot_producing_ids = [Command.set(lot.ids)]

    def _terminal_produce(self, employee, when, event):
        """Record the quantity produced (and the lot / serial number)."""
        self.ensure_one()
        self._terminal_check_open()
        messages = []
        qty = event.get('qty')
        if qty not in (None, ''):
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                raise UserError(_('The quantity produced is not a number.')) from None
            if qty < 0:
                raise UserError(_('The quantity produced cannot be negative.'))
            if qty:
                self.qty_producing = qty
                messages.append(_('Quantity produced: %(qty)s %(uom)s.', qty=qty, uom=self.product_uom_id.name))
        if 'lot' in event:
            self._terminal_set_lot(event.get('lot'))
            if self.production_id.lot_producing_ids:
                messages.append(_('Lot / serial number: %s.', ', '.join(self.production_id.lot_producing_ids.mapped('name'))))
        return ' '.join(messages) or _('Recorded by %s.', employee.name)

    def _terminal_finish(self, employee, when, event):
        self.ensure_one()
        self._terminal_check_open()
        messages = [self._terminal_produce(employee, when, event)]
        self._terminal_stop_times(self._terminal_open_times(), when)
        if self.qty_producing == 0:
            self.qty_producing = self.qty_remaining
        self.button_finish()
        messages.append(_('Finished by %s.', employee.name))
        production = self.production_id
        company = self.workcenter_id._terminal_company()
        if company.mrp_terminal_close_production and all(
                wo.state in ('done', 'cancel') for wo in production.workorder_ids):
            messages.append(production._terminal_mark_done())
        return ' '.join(filter(None, messages))


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _terminal_mark_done(self):
        """Produce the order from the Work Centre app. Anything that needs a
        decision (a wizard) is left for the office; a quantity short of the
        order goes to a backorder."""
        self.ensure_one()
        if self.product_tracking in ('lot', 'serial') and not self.lot_producing_ids:
            return _('%s needs a lot / serial number before it can be produced; finish it in Odoo.', self.name)
        partial = self.product_uom_id.compare(self.qty_producing, self.product_qty) < 0
        try:
            with self.env.cr.savepoint():
                result = self.sudo().with_context(
                    skip_redirection=True, skip_consumption=True, skip_backorder=True,
                    mo_ids_to_backorder=self.ids if partial else [],
                ).button_mark_done()
        except UserError as error:
            return _('%(order)s could not be produced: %(error)s', order=self.name, error=error.args[0])
        if isinstance(result, dict) and result.get('res_model'):
            return _('%s needs checking before it can be produced; finish it in Odoo.', self.name)
        return _('%s produced.', self.name)

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tests.common import Form


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    has_receivable_picking = fields.Boolean(
        compute='_compute_has_receivable_picking', store=True,
        help='There is an incoming receipt for this order that is not yet fully processed.',
    )

    @api.depends('picking_ids.state', 'picking_ids.picking_type_id.code')
    def _compute_has_receivable_picking(self):
        for order in self:
            order.has_receivable_picking = bool(order._get_receivable_picking())

    def _get_receivable_picking(self):
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel') and p.picking_type_id.code == 'incoming')[:1]

    def get_receivable_picking_id(self):
        self.ensure_one()
        return self._get_receivable_picking().id

    def action_open_barcode_receive(self):
        self.ensure_one()
        picking = self._get_receivable_picking()
        if not picking:
            raise UserError('There is no pending receipt to scan for this purchase order.')
        return {
            'type': 'ir.actions.client',
            'tag': 'scanner_app.home',
            'name': 'Receive by Barcode',
            'target': 'fullscreen',
            'params': {'screen': 'receive_scan', 'pickingId': picking.id},
        }

    @api.model
    def create_from_barcode_scan(self, lines):
        """Create one purchase.order per vendor from scanned cart lines.

        lines: list of dicts {product_id, partner_id, packaging_id (or False), package_qty}.
        Uses Form() to replay the standard order/line onchains (pricing, taxes, UoM,
        packaging -> qty) exactly as the UI would, rather than recomputing them by hand.
        """
        if not lines:
            raise UserError("Nothing to order - scan at least one product first.")

        grouped = {}
        for line in lines:
            grouped.setdefault(line['partner_id'], []).append(line)

        orders = self.browse()
        for partner_id, partner_lines in grouped.items():
            po_form = Form(self.env['purchase.order'])
            po_form.partner_id = self.env['res.partner'].browse(partner_id)
            for pl in partner_lines:
                product = self.env['product.product'].browse(pl['product_id'])
                with po_form.order_line.new() as line_form:
                    line_form.product_id = product
                    packaging_id = pl.get('packaging_id')
                    if packaging_id:
                        line_form.product_packaging_id = self.env['product.packaging'].browse(packaging_id)
                        line_form.product_packaging_qty = pl['package_qty']
                    else:
                        line_form.product_qty = pl['package_qty']
            orders |= po_form.save()

        return orders.mapped('name')

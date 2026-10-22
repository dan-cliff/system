from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    print3d_estimate_count = fields.Integer(compute='_compute_print3d_estimate_count')

    @api.depends('order_line.print3d_estimate_id')
    def _compute_print3d_estimate_count(self):
        for order in self:
            order.print3d_estimate_count = len(order.order_line.print3d_estimate_id)

    def action_view_print3d_estimates(self):
        self.ensure_one()
        estimates = self.order_line.print3d_estimate_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('3D Print Estimates'),
            'res_model': 'print3d.estimate',
            'view_mode': 'list,form',
            'domain': [('id', 'in', estimates.ids)],
        }

    # ── Website cart ─────────────────────────────────────────────────────
    # (these methods only exist with website_sale, which this module depends on)

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        product = self.env['product.product'].browse(product_id)
        if product.print3d_dynamic_pricing and not kwargs.get('print3d_estimate_id'):
            raise UserError(_(
                'The price of "%s" depends on your 3D file. Upload your file on the '
                'product page to get a price and add it to your cart.', product.display_name,
            ))
        return super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)

    def _cart_find_product_line(self, product_id, uom_id, linked_line_id=False,
                                no_variant_attribute_value_ids=None, **kwargs):
        lines = super()._cart_find_product_line(
            product_id, uom_id, linked_line_id=linked_line_id,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids, **kwargs,
        )
        estimate_id = kwargs.get('print3d_estimate_id')
        # Every uploaded file is its own line; the same file adds to its line.
        return lines.filtered(lambda line: line.print3d_estimate_id.id == (estimate_id or False))

    def _prepare_order_line_values(self, product_id, quantity, uom_id, **kwargs):
        values = super()._prepare_order_line_values(product_id, quantity, uom_id, **kwargs)
        estimate_id = kwargs.get('print3d_estimate_id')
        if estimate_id:
            estimate = self.env['print3d.estimate'].browse(estimate_id)
            product = self.env['product.product'].browse(values['product_id'])
            values['print3d_estimate_id'] = estimate.id
            values['name'] = '%s\n%s' % (
                product.with_context(lang=self._get_lang()).display_name,
                estimate.with_context(lang=self._get_lang())._sale_line_description(),
            )
        return values


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    print3d_estimate_id = fields.Many2one(
        'print3d.estimate',
        string='3D Print Estimate',
        index='btree_not_null',
        copy=True,
        domain="[('state', '=', 'done'), ('company_id', '=', company_id)]",
        help='The price of this line comes from the estimate of this 3D print file.',
    )
    print3d_dynamic_pricing = fields.Boolean(related='product_id.print3d_dynamic_pricing')
    print3d_filament_g = fields.Float(related='print3d_estimate_id.total_filament_g', string='Filament (g)')
    print3d_print_time = fields.Char(related='print3d_estimate_id.print_time_display', string='Print Time')

    @api.depends('print3d_estimate_id', 'print3d_estimate_id.price')
    def _compute_price_unit(self):
        return super()._compute_price_unit()

    def _get_display_price(self):
        self.ensure_one()
        estimate = self.print3d_estimate_id
        if not estimate:
            return super()._get_display_price()
        order = self.order_id
        return estimate.currency_id._convert(
            estimate.price,
            self.currency_id or order.currency_id or estimate.currency_id,
            self.company_id or estimate.company_id,
            order.date_order or fields.Date.context_today(self),
        )

    @api.onchange('print3d_estimate_id')
    def _onchange_print3d_estimate_id(self):
        for line in self:
            estimate = line.print3d_estimate_id
            if not estimate:
                continue
            if not line.product_id and estimate.product_id:
                line.product_id = estimate.product_id
            line.name = '%s\n%s' % (
                line.product_id.display_name or '', estimate._sale_line_description(),
            )

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        if self.print3d_estimate_id:
            values['print3d_estimate_id'] = self.print3d_estimate_id.id
        return values

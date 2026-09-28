from odoo import api, fields, models
from odoo.exceptions import ValidationError


class KennelBookingProduct(models.Model):
    """A product or service charged on a booking (Products tab, when invoicing is enabled)."""
    _name = 'kennel.booking.product'
    _description = 'Booking Product'
    _order = 'booking_id, sequence, id'
    _check_company_auto = True

    booking_id = fields.Many2one('kennel.booking', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    # A line that was invoiced and then removed is archived rather than deleted, so the removal can be
    # credited on the next amendment invoice.
    active = fields.Boolean(default=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True, check_company=True, domain="product_domain",
    )
    product_domain = fields.Binary(compute='_compute_product_domain')
    name = fields.Char(string='Description', compute='_compute_from_product', store=True, readonly=False)
    quantity = fields.Float(default=1.0, digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    price_unit = fields.Float(
        string='Unit Price', digits='Product Price', compute='_compute_from_product', store=True, readonly=False,
    )
    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_price_subtotal')

    # Invoicing bookkeeping (hidden): what's already on invoices and what's still to go.
    invoice_line_ids = fields.One2many('account.move.line', 'kennel_booking_product_id', string='Invoice Lines')
    qty_invoiced = fields.Float(
        string='Invoiced', digits='Product Unit', compute='_compute_qty_invoiced', store=True,
        help='Quantity on the booking\'s invoices (draft or posted), less any credited.',
    )
    qty_to_invoice = fields.Float(
        string='To Invoice', digits='Product Unit', compute='_compute_qty_invoiced', store=True,
        help='Quantity not invoiced yet; negative when the booking now has less than was invoiced.',
    )

    @api.depends_context('company')
    @api.depends('booking_id.company_id')
    def _compute_product_domain(self):
        for line in self:
            line.product_domain = (line.booking_id.company_id or self.env.company)._kennel_product_domain()

    @api.depends('product_id')
    def _compute_from_product(self):
        for line in self:
            line.name = line.product_id.get_product_multiline_description_sale() if line.product_id else False
            line.price_unit = line.product_id.lst_price

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.depends('quantity', 'active', 'invoice_line_ids.quantity', 'invoice_line_ids.move_id.state',
                 'invoice_line_ids.move_id.move_type')
    def _compute_qty_invoiced(self):
        for line in self:
            invoiced = 0.0
            for invoice_line in line.sudo().invoice_line_ids:
                move = invoice_line.move_id
                if move.state == 'cancel':
                    continue
                invoiced += invoice_line.quantity * (-1 if move.move_type == 'out_refund' else 1)
            line.qty_invoiced = invoiced
            line.qty_to_invoice = (line.quantity if line.active else 0.0) - invoiced

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(self.env._('%s: the quantity can\'t be negative.', line.product_id.display_name))

    def unlink(self):
        # Keep invoiced lines (archived) so the next amendment can credit them.
        invoiced = self.filtered(lambda line: line.sudo().invoice_line_ids)
        invoiced.write({'active': False})
        return super(KennelBookingProduct, self - invoiced).unlink()

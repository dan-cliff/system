from odoo import api, fields, models


class ModernCrmOpportunityLine(models.Model):
    _name = 'modern.crm.opportunity.line'
    _description = 'CRM Opportunity Product'
    _order = 'opportunity_id, sequence, id'

    opportunity_id = fields.Many2one(
        'modern.crm.opportunity', string='Opportunity', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='opportunity_id.company_id', store=True)
    currency_id = fields.Many2one(related='opportunity_id.currency_id')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('sale_ok', '=', True), ('company_id', 'in', (company_id, False))]")
    name = fields.Text('Description', compute='_compute_name', store=True, readonly=False)
    quantity = fields.Float('Quantity', default=1.0, digits='Product Unit')
    uom_id = fields.Many2one(
        'uom.uom', string='Unit', compute='_compute_uom_id', store=True, readonly=False)
    price_unit = fields.Monetary(
        'Sales Price', currency_field='currency_id', compute='_compute_price_unit', store=True,
        readonly=False)
    discount = fields.Float('Discount (%)', digits='Discount')
    price_subtotal = fields.Monetary(
        'Total Price', currency_field='currency_id', compute='_compute_price_subtotal', store=True)

    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.get_product_multiline_description_sale()

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id

    @api.depends('product_id', 'uom_id')
    def _compute_price_unit(self):
        for line in self:
            if not line.product_id:
                continue
            price = line.product_id.lst_price
            if line.uom_id and line.uom_id != line.product_id.uom_id:
                price = line.product_id.uom_id._compute_price(price, line.uom_id)
            line.price_unit = line.product_id.currency_id._convert(
                price, line.currency_id or line.product_id.currency_id,
                line.company_id or self.env.company, fields.Date.context_today(line))

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit * (1 - (line.discount or 0.0) / 100.0)

    def _prepare_sale_line_values(self):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'name': self.name,
            'product_uom_qty': self.quantity,
            'product_uom_id': self.uom_id.id,
            'price_unit': self.price_unit,
            'discount': self.discount,
            'sequence': self.sequence,
        }

from odoo import api, fields, models
from odoo.tools.misc import get_lang


class SaleSubscriptionLine(models.Model):
    _name = 'sale.subscription.line'
    _description = 'Subscription Product'
    _inherit = ['analytic.mixin']
    _order = 'sale_subscription_id, id'
    _check_company_auto = True

    sale_subscription_id = fields.Many2one('sale.subscription', string='Subscription', required=True,
                                           index=True, ondelete='cascade')
    company_id = fields.Many2one(related='sale_subscription_id.company_id', string='Company', store=True,
                                 index=True)
    currency_id = fields.Many2one(related='sale_subscription_id.currency_id', string='Currency', store=True)
    product_id = fields.Many2one('product.product', string='Product', check_company=True,
                                 domain="[('sale_ok', '=', True)]")
    name = fields.Char(string='Description', compute='_compute_name', store=True, readonly=False)
    product_uom_qty = fields.Float(string='Quantity', default=1.0, digits='Product Unit')
    price_unit = fields.Float(string='Unit Price', digits='Product Price',
                              compute='_compute_price_unit', store=True, readonly=False)
    discount = fields.Float(string='Discount (%)', digits='Discount')
    tax_ids = fields.Many2many('account.tax', relation='subscription_line_tax', column1='subscription_line_id',
                               column2='tax_id', string='Taxes', check_company=True,
                               domain="[('type_tax_use', '=', 'sale')]",
                               compute='_compute_tax_ids', store=True, readonly=False)
    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_amounts', store=True)
    price_total = fields.Monetary(string='Total', compute='_compute_amounts', store=True)
    amount_tax_line_amount = fields.Float(string='Taxes Amount', compute='_compute_amounts', store=True)

    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if not line.product_id:
                line.name = line.name or False
                continue
            lang = get_lang(self.env, line.sale_subscription_id.partner_id.lang).code
            line.name = line.product_id.with_context(lang=lang).get_product_multiline_description_sale()

    @api.depends('product_id', 'product_uom_qty', 'sale_subscription_id.pricelist_id')
    def _compute_price_unit(self):
        for line in self:
            product = line.product_id
            if not product:
                continue
            subscription = line.sale_subscription_id
            # without a pricelist: the sales price, in the subscription's currency
            line.price_unit = subscription.pricelist_id._get_product_price(
                product, line.product_uom_qty or 1.0,
                currency=subscription.currency_id or self.env.company.currency_id,
                uom=product.uom_id, date=fields.Date.context_today(line))

    @api.depends('product_id', 'sale_subscription_id.fiscal_position_id')
    def _compute_tax_ids(self):
        for line in self:
            company = line.company_id or self.env.company
            taxes = line.product_id.taxes_id._filter_taxes_by_company(company)
            fiscal_position = line.sale_subscription_id.fiscal_position_id
            line.tax_ids = fiscal_position.map_tax(taxes) if fiscal_position else taxes

    @api.depends('product_uom_qty', 'price_unit', 'discount', 'tax_ids', 'currency_id')
    def _compute_amounts(self):
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            currency = line.currency_id or self.env.company.currency_id
            taxes = line.tax_ids.compute_all(
                price, currency, line.product_uom_qty, product=line.product_id,
                partner=line.sale_subscription_id.partner_id)
            line.price_subtotal = taxes['total_excluded']
            line.price_total = taxes['total_included']
            line.amount_tax_line_amount = taxes['total_included'] - taxes['total_excluded']

    def _prepare_account_move_line(self):
        self.ensure_one()
        values = {
            'product_id': self.product_id.id,
            'name': self.name,
            'quantity': self.product_uom_qty,
            'price_unit': self.price_unit,
            'discount': self.discount,
            'tax_ids': [fields.Command.set(self.tax_ids.ids)],
            'analytic_distribution': self.analytic_distribution,
        }
        if self.product_id:
            values['product_uom_id'] = self.product_id.uom_id.id
        return values

    def _prepare_sale_order_line(self):
        self.ensure_one()
        values = {
            'product_id': self.product_id.id,
            'name': self.name,
            'product_uom_qty': self.product_uom_qty,
            'price_unit': self.price_unit,
            'discount': self.discount,
            'tax_ids': [fields.Command.set(self.tax_ids.ids)],
            'analytic_distribution': self.analytic_distribution,
        }
        if self.product_id:
            values['product_uom_id'] = self.product_id.uom_id.id
        return values

"""Subscriptions on the records around them: products that are sold as a
subscription, the sales orders that start subscriptions (and the ones the
subscriptions raise), their invoices and the customers."""
from collections import defaultdict

from odoo import Command, api, fields, models

SUBSCRIPTION_GROUP = 'advanced_accounting.group_subscription_user'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    subscribable = fields.Boolean(string='Subscription Product',
                                  help="Confirming a sales order of this product starts a subscription for it.")
    subscription_template_id = fields.Many2one('sale.subscription.template', string='Subscription Template',
                                               help="How the subscriptions of this product recur and are billed.")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # the subscriptions this order started
    subscription_ids = fields.One2many('sale.subscription', 'sale_order_id', string='Subscriptions')
    subscriptions_count = fields.Integer(string='Subscription Count', compute='_compute_subscriptions_count')
    # the subscription that raised this order (invoicing by sales order)
    order_subscription_id = fields.Many2one('sale.subscription', string='Subscription', copy=False,
                                            index='btree_not_null')

    @api.depends('subscription_ids')
    def _compute_subscriptions_count(self):
        counts = dict(self.env['sale.subscription'].sudo()._read_group(
            [('sale_order_id', 'in', self.ids)], ['sale_order_id'], ['__count']))
        for order in self:
            order.subscriptions_count = counts.get(order._origin, 0)

    def action_view_subscriptions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_accounting.sale_subscription_action')
        action.update({'domain': [('sale_order_id', '=', self.id)], 'context': {'create': False}})
        if len(self.subscription_ids) == 1:
            action.update({'views': [(False, 'form')], 'view_mode': 'form', 'res_id': self.subscription_ids.id})
        return action

    def _subscription_lines_by_template(self):
        """ The order's subscription products, by subscription template. """
        grouped = defaultdict(lambda: self.env['sale.order.line'])
        for line in self.order_line:
            template = line.product_id.product_tmpl_id
            if template.subscribable and template.subscription_template_id and not line.display_type:
                grouped[template.subscription_template_id] |= line
        return grouped

    def _prepare_subscription(self, template, lines):
        self.ensure_one()
        return {
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'user_id': (self.user_id or self.env.user).id,
            'crm_team_id': self.team_id.id,
            'template_id': template.id,
            'pricelist_id': self.pricelist_id.id or self.partner_id.with_company(
                self.company_id).property_product_pricelist.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'date_start': fields.Date.context_today(self),
            'sale_order_id': self.id,
            'sale_subscription_line_ids': [Command.create(line._prepare_subscription_line()) for line in lines],
        }

    def create_subscriptions(self):
        """ A running subscription per subscription template of the order's
        products. The order invoices the first period, so the subscription is
        first invoiced one period later. Made as the superuser: confirming an
        order is a Sales right, whatever the salesperson can do in
        Subscriptions. """
        subscriptions = self.env['sale.subscription'].sudo()
        for order in self.sudo():
            for template, lines in order._subscription_lines_by_template().items():
                subscription = subscriptions.with_company(order.company_id).create(
                    order._prepare_subscription(template, lines))
                subscription.action_start_subscription()
                subscription.recurring_next_date = subscription._get_next_invoice_date(subscription.date_start)
                subscriptions |= subscription
        return subscriptions

    def action_confirm(self):
        result = super().action_confirm()
        # the orders of a subscription invoice it: they don't start new ones
        self.filtered(lambda order: not order.order_subscription_id).create_subscriptions()
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_subscription_line(self):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'name': self.name,
            'product_uom_qty': self.product_uom_qty,
            'price_unit': self.price_unit,
            'discount': self.discount,
            'tax_ids': [Command.set(self.tax_ids.ids)],
            'analytic_distribution': self.analytic_distribution,
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_id = fields.Many2one('sale.subscription', string='Subscription', copy=False,
                                      index='btree_not_null')

    def action_open_subscription(self):
        self.ensure_one()
        return self.subscription_id.get_formview_action()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    subscription_ids = fields.One2many('sale.subscription', 'partner_id', string='Subscriptions')
    subscription_count = fields.Integer(string='Subscription Count', compute='_compute_subscription_count')

    def _compute_subscription_count(self):
        # the subscriptions of the partner and of its contacts
        Subscription = self.env['sale.subscription'].sudo()
        for partner in self:
            partner.subscription_count = Subscription.search_count(
                [('partner_id', 'child_of', partner._origin.id)]) if partner._origin.id else 0

    def action_view_subscription_ids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_accounting.sale_subscription_action')
        action.update({
            'domain': [('partner_id', 'child_of', self.id)],
            'context': {'default_partner_id': self.id},
        })
        return action

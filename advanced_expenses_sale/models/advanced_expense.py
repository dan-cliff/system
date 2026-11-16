from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvancedExpense(models.Model):
    _inherit = 'advanced.expense'

    sale_order_id = fields.Many2one(
        'sale.order', string='Customer to Re-invoice', index='btree_not_null', tracking=True,
        check_company=True,
        domain="[('state', '=', 'sale'), ('company_id', '=', company_id)]",
        help='A confirmed sales order: approving the expense adds it to the order to be invoiced.')
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sales Order Line', readonly=True,
                                         copy=False, index='btree_not_null')

    def _on_approved(self):
        for expense in self.filtered(lambda e: e.sale_order_id and not e.sale_order_line_id):
            expense.sudo()._add_sale_order_line()
        return super()._on_approved()

    def _sale_line_vals(self):
        self.ensure_one()
        order = self.sale_order_id
        product = self.category_id.sale_product_id \
            or self.env.ref('advanced_expenses_sale.product_reinvoiced_expense')
        price = self.currency_id._convert(self.total_amount, order.currency_id, order.company_id,
                                          self.date or fields.Date.context_today(self))
        return {
            'order_id': order.id,
            'product_id': product.id,
            'name': '%s %s' % (self.reference, self.name),
            'product_uom_qty': 1.0,
            'price_unit': price,
            'tax_ids': [(5, 0, 0)],
            'is_expense': True,
            'sequence': 999,
        }

    def _add_sale_order_line(self):
        self.ensure_one()
        order = self.sale_order_id
        if order.state != 'sale':
            raise UserError(_('%(order)s is not a confirmed sales order, so %(expense)s cannot be re-invoiced on it.',
                              order=order.name, expense=self.display_name))
        if order.locked:
            raise UserError(_('%(order)s is locked: unlock it to re-invoice %(expense)s.',
                              order=order.name, expense=self.display_name))
        line = self.env['sale.order.line'].create(self._sale_line_vals())
        self.sale_order_line_id = line
        order.message_post(body=_('Expense %s added to be re-invoiced.', self._get_html_link()))

    def _on_reset(self):
        for expense in self.filtered('sale_order_line_id'):
            line = expense.sale_order_line_id.sudo()
            if line.qty_invoiced:
                raise UserError(_('%s has already been invoiced to the customer.', expense.display_name))
            expense.sudo().sale_order_line_id = False
            if line._check_line_unlink():
                # Confirmed orders keep their lines: nothing is left to invoice.
                line.write({'product_uom_qty': 0.0, 'name': _('%s (reset)', line.name)})
            else:
                line.unlink()
        return super()._on_reset()

    def write(self, vals):
        if 'sale_order_id' in vals and self.filtered('sale_order_line_id'):
            raise UserError(_('This expense is already on a sales order. Reset it to draft to change the order.'))
        return super().write(vals)

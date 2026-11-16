from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    advanced_expense_ids = fields.One2many('advanced.expense', 'sale_order_id', string='Expenses')
    advanced_expense_count = fields.Integer(compute='_compute_advanced_expense_count')

    def _compute_advanced_expense_count(self):
        counts = dict(self.env['advanced.expense'].sudo()._read_group(
            [('sale_order_id', 'in', self.ids)], ['sale_order_id'], ['__count']))
        for order in self:
            order.advanced_expense_count = counts.get(order, 0)

    def action_open_advanced_expenses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expenses'),
            'res_model': 'advanced.expense',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    advanced_expense_ids = fields.One2many('advanced.expense', 'sale_order_line_id', string='Expenses')

# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Stock of the line's product (variant), for the order lines list.
    purchasing_qty_on_hand = fields.Float(
        'On Hand', related='product_id.qty_available', digits='Product Unit')
    purchasing_qty_forecast = fields.Float(
        'Forecast', related='product_id.virtual_available', digits='Product Unit')

# -*- coding: utf-8 -*-
from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_approve(self, force=False):
        # purchase_stock's button_approve creates the receipts after ours has run,
        # with the approver's own rights, which may not reach Inventory. Check the
        # approval here, above it, so receipt creation runs with sudo() too.
        return self._purchasing_approve(
            lambda orders: super(PurchaseOrder, orders).button_approve(force=force))

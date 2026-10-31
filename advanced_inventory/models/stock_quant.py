# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'walk':
            return False
        return super()._get_removal_strategy_order(removal_strategy)

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, qty=0):
        quants = super()._gather(product_id, location_id, lot_id=lot_id, package_id=package_id,
                                 owner_id=owner_id, strict=strict, qty=qty)
        if self._get_removal_strategy(product_id, location_id) == 'walk':
            # Reserve from the locations first on the walk, so a pick list is one pass.
            quants = quants.sorted(lambda q: (q.location_id.walk_sequence, q.in_date or q.create_date, q.id))
            quants = quants.sorted(lambda q: not q.lot_id)
        return quants

    def action_apply_inventory(self, date=None):
        user = self.env.user
        if (not self.env.su and user.has_group('advanced_inventory.group_inventory_user')
                and not user.has_group('advanced_inventory.group_adjustment_apply')):
            raise UserError(_('Applying counted quantities needs the "Inventory Adjustments: Apply" permission.'))
        return super().action_apply_inventory(date=date)

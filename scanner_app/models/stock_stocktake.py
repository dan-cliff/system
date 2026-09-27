from odoo import models


class StockStocktake(models.Model):
    _inherit = 'stock.stocktake'

    def action_open_barcode_scan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'scanner_app.home',
            'name': 'Scan Products',
            'target': 'fullscreen',
            'params': {'screen': 'stocktake_scan', 'stocktakeId': self.id},
        }

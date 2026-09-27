from odoo import api, fields, models


class StockStocktakeLine(models.Model):
    _name = 'stock.stocktake.line'
    _description = 'Stocktake Line'
    _order = 'id'

    stocktake_id = fields.Many2one(
        'stock.stocktake', string='Stocktake', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='stocktake_id.company_id', store=True)
    state = fields.Selection(related='stocktake_id.state')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('is_storable', '=', True)]")
    barcode = fields.Char(related='product_id.barcode', readonly=True)
    tracking = fields.Selection(related='product_id.tracking', readonly=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', string='Unit of Measure', readonly=True)
    lot_id = fields.Many2one(
        'stock.lot', string='Lot/Serial', domain="[('product_id', '=', product_id)]")
    counted_qty = fields.Float(string='Counted Quantity', default=0.0)
    theoretical_qty = fields.Float(string='On Hand', compute='_compute_theoretical_qty')
    difference_qty = fields.Float(string='Difference', compute='_compute_theoretical_qty')

    _sql_constraints = [
        ('counted_qty_positive', 'CHECK(counted_qty >= 0)', 'Counted quantity cannot be negative.'),
        ('unique_product_lot', 'unique(stocktake_id, product_id, lot_id)',
         'This product (and lot/serial) already has a line on this stocktake.'),
    ]

    @api.depends('product_id', 'lot_id', 'stocktake_id.location_id', 'stocktake_id.warehouse_id',
                 'stocktake_id.company_id', 'counted_qty')
    def _compute_theoretical_qty(self):
        for line in self:
            location = line.stocktake_id._get_target_location() if line.stocktake_id else False
            if not location or not line.product_id:
                line.theoretical_qty = 0.0
            else:
                domain = [
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', location.id),
                    ('company_id', '=', line.stocktake_id.company_id.id),
                ]
                if line.lot_id:
                    domain.append(('lot_id', '=', line.lot_id.id))
                quants = self.env['stock.quant'].search(domain)
                line.theoretical_qty = sum(quants.mapped('quantity'))
            line.difference_qty = line.counted_qty - line.theoretical_qty

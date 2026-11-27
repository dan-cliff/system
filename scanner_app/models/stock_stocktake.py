from odoo import models
from odoo.exceptions import UserError


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

    def _find_scanned_product(self, barcode):
        """Fall back to the Vendor Product Code on Product > Purchase > Vendors when no
        product has this barcode: bulk packs (cartons, cases, ...) are stored under the
        vendor's code, and one scan counts one of that vendor line's Unit, converted to
        the product's own unit (e.g. a carton of 24 adds 24 Units)."""
        found = super()._find_scanned_product(barcode)
        if found.get('product') or found.get('error'):
            return found

        sellers = self.env['product.supplierinfo'].search([
            ('product_code', '=', barcode),
            ('company_id', 'in', (self.company_id.id, False)),
        ])
        if not sellers:
            return found

        products = self.env['product.product']
        seller_by_product = {}
        for seller in sellers:
            if seller.product_id:
                variants = seller.product_id
            else:
                variants = seller.product_tmpl_id.product_variant_ids
            if len(variants) != 1:
                return {
                    'product': products,
                    'qty': 0.0,
                    'error': 'Vendor code "%s" is set on "%s", which has several variants - '
                             'set the Variant on its Vendor line to scan it.'
                             % (barcode, seller.product_tmpl_id.display_name),
                }
            seller_by_product.setdefault(variants.id, seller)
            products |= variants

        if len(products) > 1:
            return {
                'product': self.env['product.product'],
                'qty': 0.0,
                'error': 'Vendor code "%s" is used by more than one product (%s).'
                         % (barcode, ', '.join(products.mapped('display_name'))),
            }

        seller = seller_by_product[products.id]
        seller_uom = self._seller_uom(seller) or products.uom_id
        try:
            qty = seller_uom._compute_quantity(1.0, products.uom_id, round=False)
        except UserError:
            return {
                'product': self.env['product.product'],
                'qty': 0.0,
                'error': 'Vendor code "%s" uses the unit "%s", which can\'t be converted to '
                         '"%s" for %s.' % (barcode, seller_uom.name, products.uom_id.name,
                                           products.display_name),
            }
        result = {'product': products, 'qty': qty}
        if seller_uom != products.uom_id:
            result['uom_name'] = seller_uom.name
        return result

    def _seller_uom(self, seller):
        # The Vendor line's "Unit" field was renamed across Odoo versions.
        for field_name in ('product_uom_id', 'product_uom'):
            if field_name in seller._fields:
                return seller[field_name]
        return self.env['uom.uom']

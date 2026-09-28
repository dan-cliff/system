from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kennel_warehouse_ids = fields.Many2many(
        'stock.warehouse', 'kennel_warehouse_company_rel', 'company_id', 'warehouse_id', string='Warehouse/s',
    )
    kennel_product_categ_ids = fields.Many2many(
        'product.category', 'kennel_product_categ_company_rel', 'company_id', 'categ_id',
        string='Product Categories',
        help='Only products in these categories (or their sub-categories) can be added to bookings.',
    )

    def _kennel_product_domain(self):
        """Products offered on bookings: saleable ones in the kennel's product categories (all saleable
        products while no category is set)."""
        self.ensure_one()
        domain = [('sale_ok', '=', True), ('company_id', 'in', [False, self.id])]
        if self.kennel_product_categ_ids:
            domain.append(('categ_id', 'child_of', self.kennel_product_categ_ids.ids))
        return domain

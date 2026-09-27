from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    zoo_feed_warehouse_ids = fields.Many2many(
        'stock.warehouse', 'zoo_feed_warehouse_company_rel', 'company_id', 'warehouse_id',
        string='Feed Warehouses',
        help='Which Warehouse/s are feed items stored in?',
    )
    zoo_feed_categ_ids = fields.Many2many(
        'product.category', 'zoo_feed_categ_company_rel', 'company_id', 'categ_id',
        string='Feed Product Categories',
        help='Which Product Categories contain Feed items?',
    )

    zoo_feed_location_id = fields.Many2one(
        'stock.location', string='Animal Feed Location', readonly=True,
        help='Where feed goes when a feeding round is marked Fed.',
    )

    def _zoo_feed_location(self):
        """The consumption location feed is moved to when animals are fed,
        created on first use."""
        self.ensure_one()
        if not self.zoo_feed_location_id:
            self.sudo().zoo_feed_location_id = self.env['stock.location'].sudo().create({
                'name': self.env._('Animal Feed'),
                'usage': 'inventory',
                'company_id': self.id,
            })
        return self.zoo_feed_location_id

    def _zoo_feed_product_domain(self):
        """Domain for the products offered as feed: products in the feed
        categories (or their sub-categories) that are stocked in one of the
        feed warehouses. An empty setting doesn't filter on it."""
        self.ensure_one()
        domain = []
        if self.zoo_feed_categ_ids:
            domain.append(('categ_id', 'child_of', self.zoo_feed_categ_ids.ids))
        if self.zoo_feed_warehouse_ids:
            # Products have no warehouse of their own: a product is "in" a
            # warehouse when it has stock records in any of its locations.
            stocked = self.env['stock.quant'].sudo()._read_group(
                [('location_id', 'child_of', self.zoo_feed_warehouse_ids.view_location_id.ids)],
                ['product_id'],
            )
            domain.append(('id', 'in', [product.id for product, in stocked]))
        return domain

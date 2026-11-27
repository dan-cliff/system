# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class MrpWorkcenterCapacity(models.Model):
    """Product capacities for a product (template), one of its variants, a
    product category or all products. The most specific line applies."""
    _inherit = 'mrp.workcenter.capacity'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', compute='_compute_product_tmpl_id', store=True,
        readonly=False, precompute=True, index='btree_not_null',
        help='Every variant of this product, unless a line names the variant.',
    )
    product_id = fields.Many2one(string='Variant')
    product_categ_id = fields.Many2one(
        'product.category', string='Product Category', index='btree_not_null',
        help='Every product in this category (and its sub-categories) without a line of its own.',
    )

    # Odoo's index allowed one line per variant (or all products) and unit;
    # products and categories each get their own line too.
    _workcenter_product_product_uom_unique = models.UniqueIndex(
        '(workcenter_id, COALESCE(product_id, 0), COALESCE(product_tmpl_id, 0), '
        'COALESCE(product_categ_id, 0), product_uom_id)',
        'Product/Unit capacity should be unique for each workcenter.',
    )

    @api.depends('product_id')
    def _compute_product_tmpl_id(self):
        for capacity in self:
            capacity.product_tmpl_id = capacity.product_id.product_tmpl_id or capacity.product_tmpl_id

    @api.depends('product_id', 'product_tmpl_id')
    def _compute_product_uom_id(self):
        super()._compute_product_uom_id()
        for capacity in self.filtered(lambda c: not c.product_id and c.product_tmpl_id):
            capacity.product_uom_id = capacity.product_tmpl_id.uom_id

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        if self.product_id and self.product_id.product_tmpl_id != self.product_tmpl_id:
            self.product_id = False

    @api.constrains('product_id', 'product_tmpl_id', 'product_categ_id')
    def _check_product_or_category(self):
        for capacity in self:
            if capacity.product_categ_id and capacity.product_tmpl_id:
                raise ValidationError(_('A capacity line is for a product or a product category, not both.'))
            if capacity.product_id and capacity.product_id.product_tmpl_id != capacity.product_tmpl_id:
                raise ValidationError(_('The variant %s is not a variant of the product on its line.',
                                        capacity.product_id.display_name))


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    def _capacity_rank(self, capacity, product, unit):
        """How well a capacity line fits (lower is better), or None when it doesn't."""
        if capacity.product_uom_id not in (product.uom_id | (unit or product.uom_id)):
            return None
        if capacity.product_id:
            return 0 if capacity.product_id == product else None
        if capacity.product_tmpl_id:
            return 1 if capacity.product_tmpl_id == product.product_tmpl_id else None
        if capacity.product_categ_id:
            chain = [int(i) for i in reversed((product.categ_id.parent_path or '').split('/')) if i]
            if capacity.product_categ_id.id not in chain:
                return None
            return 2 + chain.index(capacity.product_categ_id.id)
        # All products: in the unit asked for first (as Odoo does).
        return 1000 if unit and capacity.product_uom_id == unit else 1001

    def _get_capacity(self, product, unit, default_capacity=1):
        if not product:
            return super()._get_capacity(product, unit, default_capacity)
        ranked = []
        for capacity in self.capacity_ids:
            rank = self._capacity_rank(capacity, product, unit)
            if rank is not None:
                ranked.append((rank, capacity.id, capacity))
        if not ranked:
            return (default_capacity, self.time_start, self.time_stop)
        capacity = min(ranked, key=lambda r: r[:2])[2]
        if float_is_zero(capacity.capacity, 0):
            return (default_capacity, capacity.time_start, capacity.time_stop)
        return (capacity.product_uom_id._compute_quantity(capacity.capacity, unit or capacity.product_uom_id),
                capacity.time_start, capacity.time_stop)

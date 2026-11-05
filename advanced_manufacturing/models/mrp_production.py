# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

GROUP_PRODUCE = 'advanced_manufacturing.group_production_produce'
GROUP_USER = 'advanced_manufacturing.group_manufacturing_user'


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    # New orders take the user's home Organisation units, not their product's.
    _org_parent_field = False

    # The form picks the product (template) first, then its variant, as the
    # Bill of Materials form does; the variant then finds the first BoM.
    mrp_product_tmpl_id = fields.Many2one(
        'product.template', string='Product', compute='_compute_mrp_product_tmpl_id', store=True,
        readonly=False, precompute=True, check_company=True, index=True,
        domain="[('type', '=', 'consu')]",
        help='The product to make. Then choose its variant (when it has several).',
    )

    @api.depends('product_id')
    def _compute_mrp_product_tmpl_id(self):
        for production in self:
            # Keep the chosen product while its variant is still to be picked.
            production.mrp_product_tmpl_id = production.product_id.product_tmpl_id or production.mrp_product_tmpl_id

    @api.onchange('mrp_product_tmpl_id')
    def _onchange_mrp_product_tmpl_id(self):
        template = self.mrp_product_tmpl_id
        if not template:
            self.product_id = False
            return
        if self.product_id.product_tmpl_id == template:
            return
        variants = template.product_variant_ids
        # One variant: it is the product. Several: the user picks one next.
        self.product_id = variants if len(variants) == 1 else False
        if not self.product_id:
            self.bom_id = False

    def _check_produce_permission(self):
        """Manufacturing Orders: Produce. Users given Manufacturing permissions
        need it to mark orders as done; the Work Centre app (which runs with
        the server's rights) and users of Odoo's own Manufacturing groups only
        are not affected."""
        user = self.env.user
        if self.env.su or not user.has_group(GROUP_USER) or user.has_group(GROUP_PRODUCE):
            return
        raise AccessError(_('You need the "Manufacturing Orders: Produce" permission to mark manufacturing orders as done.'))

    def button_mark_done(self):
        self._check_produce_permission()
        return super().button_mark_done()


class MrpBom(models.Model):
    _inherit = 'mrp.bom'
    _org_parent_field = False


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'
    _org_parent_field = False

# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        product = self.env['product.product'].browse(product_id)
        if product.product_tmpl_id.laser_shop_personalised and not kwargs.get('laser_job_id'):
            raise UserError(_(
                '"%s" is personalised. Fill in your personalisation on the product page and add it to '
                'your cart from there.', product.display_name,
            ))
        return super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)

    def _cart_find_product_line(self, product_id, uom_id, linked_line_id=False,
                                no_variant_attribute_value_ids=None, **kwargs):
        lines = super()._cart_find_product_line(
            product_id, uom_id, linked_line_id=linked_line_id,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids, **kwargs,
        )
        # Every personalisation is its own line; the same one adds to its line.
        job_id = kwargs.get('laser_job_id')
        return lines.filtered(lambda line: line.laser_job_id.id == (job_id or False))

    def _prepare_order_line_values(self, product_id, quantity, uom_id, **kwargs):
        values = super()._prepare_order_line_values(product_id, quantity, uom_id, **kwargs)
        job_id = kwargs.get('laser_job_id')
        if job_id:
            job = self.env['laser.job'].sudo().browse(job_id)
            product = self.env['product.product'].browse(values['product_id'])
            values['laser_job_id'] = job.id
            summary = job._laser_description()
            name = product.with_context(lang=self._get_lang()).display_name
            values['name'] = '%s\n%s' % (name, summary) if summary else name
        return values

# -*- coding: utf-8 -*-
import json

from odoo import fields, models

from odoo.addons.laser_jobbing.models.laser_template import VISUAL_EDITOR_PORTAL_PARAM, param_enabled
from odoo.addons.laser_jobbing.tools import formats


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    laser_shop_personalised = fields.Boolean(
        compute='_compute_laser_shop_personalised', compute_sudo=True,
        help='Customers personalise this product on its product page before adding it to the cart.',
    )

    def _compute_laser_shop_personalised(self):
        for product in self:
            product.laser_shop_personalised = bool(product.laser_template_id.customer_element_count)

    def _laser_shop_editor(self):
        """What the product page's personaliser needs (rendered as JSON in the page)."""
        self.ensure_one()
        template = self.sudo().laser_template_id
        data = template.laser_editor_data(customer_only=True)
        return {
            'data': data,
            'data_json': json.dumps(data),
            'elements': template.element_ids.filtered('customer_editable'),
            'accept': formats.accept_attribute(template.operation),
            'visual': param_enabled(self.env, VISUAL_EDITOR_PORTAL_PARAM),
            'max_mb': self.env['ir.config_parameter'].sudo().get_param('laser_jobbing.max_upload_mb') or 20,
        }

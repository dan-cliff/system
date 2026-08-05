# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_membership = fields.Boolean(
        string='Membership Product',
        help='Enable to configure this product as a membership type.',
        default=False,
    )

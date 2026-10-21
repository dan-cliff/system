# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    embroidery_dynamic_pricing = fields.Boolean(
        string='Embroidery Dynamic Pricing',
        help='The price is worked out from a submitted .pes file: customers upload their design '
             'on the website, and sales lines take the price of the attached submission.',
    )
    embroidery_profile_id = fields.Many2one(
        'embroidery.pricing.profile',
        string='Embroidery Pricing Profile',
        help='Pricing used for this product. Leave empty to use the company default.',
    )

    # ── Website helpers (used by the quote widget) ────────────────────────

    @api.model
    def _embroidery_max_upload_mb(self):
        value = self.env['ir.config_parameter'].sudo().get_param('embroidery_submission.max_upload_mb')
        try:
            return max(int(value or 10), 1)
        except ValueError:
            return 10

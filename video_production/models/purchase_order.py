# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    video_production_id = fields.Many2one(
        'video.production',
        string='Video Production',
        tracking=True,
        help='Video production this purchase order is linked to.',
        ondelete='set null',
    )

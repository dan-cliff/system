# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    membership_instant_booking_product_id = fields.Many2one(
        'product.product',
        string='Instant Booking Product',
        help='Product used when creating instant bookings from membership kiosk scans',
        domain="[('is_tour_booking', '=', True)]",
        config_parameter='membership.instant_booking_product_id',
    )

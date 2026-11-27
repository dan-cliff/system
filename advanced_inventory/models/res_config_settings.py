# -*- coding: utf-8 -*-
from odoo import fields, models

from .barcode_lookup import KEY_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Inventory's own Barcode Database (Odoo's "Stock Barcode Database" needs Enterprise).
    inventory_barcodelookup_api_key = fields.Char(
        string='Barcode Database API Key', config_parameter=KEY_PARAM,
        help='Your barcodelookup.com API key. With a key, a product\'s name, description, picture, '
             'weight and category are filled in from its barcode.')

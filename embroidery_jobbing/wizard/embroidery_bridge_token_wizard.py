# -*- coding: utf-8 -*-
from odoo import fields, models


class EmbroideryBridgeTokenWizard(models.TransientModel):
    """Shows a bridge's new access token, once."""
    _name = 'embroidery.bridge.token.wizard'
    _description = 'Embroidery Bridge Access Token'

    bridge_id = fields.Many2one('embroidery.bridge', required=True, readonly=True)
    token = fields.Char(readonly=True)
    odoo_url = fields.Char(string='Odoo Address', readonly=True)

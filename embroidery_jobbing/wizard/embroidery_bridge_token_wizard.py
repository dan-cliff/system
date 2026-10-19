# -*- coding: utf-8 -*-
import shlex

from odoo import api, fields, models


class EmbroideryBridgeTokenWizard(models.TransientModel):
    """Shows a bridge's new access token, once."""
    _name = 'embroidery.bridge.token.wizard'
    _description = 'Embroidery Bridge Access Token'

    bridge_id = fields.Many2one('embroidery.bridge', required=True, readonly=True)
    token = fields.Char(readonly=True)
    odoo_url = fields.Char(string='Odoo Address', readonly=True)
    install_command = fields.Char(compute='_compute_install_command', string='Install Command')

    @api.depends('odoo_url', 'token')
    def _compute_install_command(self):
        for wizard in self:
            url = (wizard.odoo_url or '').rstrip('/')
            wizard.install_command = 'curl -fsSL %s/embroidery/bridge/install.sh | sudo bash -s -- --url %s --token %s' % (
                shlex.quote(url), shlex.quote(url), shlex.quote(wizard.token or ''))

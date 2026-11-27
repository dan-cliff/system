# -*- coding: utf-8 -*-
import urllib.parse

from odoo import fields, models


class IotNodePairWizard(models.TransientModel):
    """Shows a one-time pairing code and the command that installs the Node."""
    _name = 'iot.node.pair.wizard'
    _description = 'Pair an IoT Node'

    node_id = fields.Many2one('iot.node', string='Node', readonly=True)
    role = fields.Selection(related='node_id.role')
    code = fields.Char(string='Pairing Code', readonly=True)
    expires = fields.Datetime(readonly=True)
    install_command = fields.Char(readonly=True)
    already_paired = fields.Boolean(readonly=True)
    is_browser_node = fields.Boolean(readonly=True)
    qr_code_url = fields.Char(compute='_compute_qr_code_url')

    def _compute_qr_code_url(self):
        for wizard in self:
            wizard.qr_code_url = '/report/barcode/?barcode_type=QR&value=%s&width=300&height=300' % (
                urllib.parse.quote(wizard.install_command or '', safe='')) if wizard.is_browser_node else False

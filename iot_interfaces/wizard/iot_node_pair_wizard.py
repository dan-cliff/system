# -*- coding: utf-8 -*-
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

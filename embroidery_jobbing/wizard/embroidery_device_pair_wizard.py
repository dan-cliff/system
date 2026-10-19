# -*- coding: utf-8 -*-
from odoo import fields, models


class EmbroideryDevicePairWizard(models.TransientModel):
    """Shows a one-time pairing code and the command that installs the Pi."""
    _name = 'embroidery.device.pair.wizard'
    _description = 'Pair a Raspberry Pi'

    name = fields.Char(string='Raspberry Pi', readonly=True)
    code = fields.Char(string='Pairing Code', readonly=True)
    expires = fields.Datetime(readonly=True)
    install_command = fields.Char(readonly=True)
    already_paired = fields.Boolean(readonly=True)

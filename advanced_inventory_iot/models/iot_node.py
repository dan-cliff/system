# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

ROLE_SIGN = 'inventory_sign'


class IotNode(models.Model):
    """Inventory's Node role: a Raspberry Pi showing a digital sign on its screen.
    Its settings live on the Node, in IoT Interfaces."""
    _inherit = 'iot.node'

    role = fields.Selection(
        selection_add=[(ROLE_SIGN, 'Inventory Digital Sign')],
        ondelete={ROLE_SIGN: 'set default'},
    )
    inventory_sign_id = fields.Many2one(
        'advanced.inventory.sign', string='Digital Sign', ondelete='restrict', tracking=True,
        help='What the screen shows. Change it here and the screen switches within a few seconds. '
             'Until one is chosen the screen waits for it.')
    inventory_screen_size = fields.Char(string='Screen Size', readonly=True, copy=False,
                                        help='Screen size the Node reported, in pixels.')
    inventory_reload_counter = fields.Integer(readonly=True, copy=False)

    def action_inventory_reload_screen(self):
        """Make the screen reload the page (e.g. after an update)."""
        for node in self:
            node.inventory_reload_counter += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('The screen reloads within a minute.')},
        }


class IotProgram(models.Model):
    _inherit = 'iot.program'

    @api.model
    def _iot_builtin_programs(self):
        programs = super()._iot_builtin_programs()
        programs[ROLE_SIGN] = {
            'name': 'Inventory Digital Sign',
            'description': "Shows an Inventory digital sign full screen on the Node's screen.",
            'folder': 'advanced_inventory_iot/node_programs/inventory_sign',
        }
        return programs

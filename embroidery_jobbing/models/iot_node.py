# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ROLE_BRIDGE = 'embroidery_bridge'
ROLE_DISPLAY = 'embroidery_display'


class IotNode(models.Model):
    """Embroidery's two Node roles: the bridge beside the machines and the
    display screen. Their settings live on the Node, in IoT Interfaces."""
    _inherit = 'iot.node'

    role = fields.Selection(
        selection_add=[(ROLE_BRIDGE, 'Embroidery Bridge'), (ROLE_DISPLAY, 'Display Screen')],
        ondelete={ROLE_BRIDGE: 'set default', ROLE_DISPLAY: 'set default'},
    )
    # ── Embroidery Bridge ─────────────────────────────────────────────────
    embroidery_machine_ids = fields.One2many('embroidery.machine', 'bridge_id', string='Embroidery Machines')
    # ── Display Screen ────────────────────────────────────────────────────
    embroidery_board_id = fields.Many2one(
        'embroidery.status.board', string='Status Board', ondelete='restrict', tracking=True,
        help='What the screen shows. Change it here and the screen switches within a few seconds.',
    )
    screen_size = fields.Char(readonly=True, copy=False, help='Screen size the display reported, in pixels.')
    reload_counter = fields.Integer(readonly=True, copy=False)

    @api.constrains('role', 'embroidery_board_id')
    def _check_embroidery_board(self):
        for node in self:
            if node.role == ROLE_DISPLAY and not node.embroidery_board_id:
                raise ValidationError(_('Choose the status board %s shows.', node.name))

    def action_reload_screen(self):
        """Make the screen reload the page (e.g. after an update)."""
        for node in self:
            node.reload_counter += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('The screen reloads within a few seconds.')},
        }


class IotProgram(models.Model):
    _inherit = 'iot.program'

    @api.model
    def _iot_builtin_programs(self):
        programs = super()._iot_builtin_programs()
        programs[ROLE_BRIDGE] = {
            'name': 'Embroidery Bridge',
            'description': 'Delivers the designs sent to the embroidery machines and reports their progress.',
            'folder': 'embroidery_jobbing/node_programs/embroidery_bridge',
        }
        programs[ROLE_DISPLAY] = {
            'name': 'Display Screen',
            'description': "Shows a status board or dashboard full screen on the Node's TV.",
            'folder': 'embroidery_jobbing/node_programs/embroidery_display',
        }
        return programs

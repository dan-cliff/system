# -*- coding: utf-8 -*-
from odoo import api, fields, models

ROLE_DISPLAY = 'video_rooms_display'


class IotNode(models.Model):
    """The Room Display: the PC behind the TV wall, an IoT Interfaces Node."""
    _inherit = 'iot.node'

    role = fields.Selection(selection_add=[(ROLE_DISPLAY, 'Video Room Display')],
                            ondelete={ROLE_DISPLAY: 'set default'})
    video_room_ids = fields.One2many('video.room', 'display_node_id', string='Room')
    # Reported by the Display on each sync.
    video_room_state = fields.Json(readonly=True, copy=False,
                                   help='Devices found, screens, driver versions, current call state.')


class IotProgram(models.Model):
    _inherit = 'iot.program'

    @api.model
    def _iot_builtin_programs(self):
        programs = super()._iot_builtin_programs()
        programs[ROLE_DISPLAY] = {
            'name': 'Video Room Display',
            'description': 'Runs meetings full screen on the TV wall in a managed Chrome with the Video Rooms '
                           'extension, and carries out commands from the Room Console.',
            'folder': 'video_rooms/node_programs/video_rooms_display',
        }
        return programs

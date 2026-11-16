# -*- coding: utf-8 -*-
from odoo import api, fields, models

ROLE_DISPLAY = 'video_rooms_display'
# Browser Nodes (DESIGN.md §7): tablets / screens that pair from a web page, sign with a
# non-extractable WebCrypto key and are signed in automatically as their restricted user.
ROLE_CONSOLE = 'video_rooms_console'
ROLE_PRESENCE = 'video_rooms_presence'
ROLE_BOARD = 'video_rooms_board'
BROWSER_ROLES = (ROLE_CONSOLE, ROLE_PRESENCE, ROLE_BOARD)


class IotNode(models.Model):
    """The Room Display: the PC behind the TV wall, an IoT Interfaces Node."""
    _inherit = 'iot.node'

    role = fields.Selection(
        selection_add=[(ROLE_DISPLAY, 'Video Room Display'), (ROLE_CONSOLE, 'Video Room Console Tablet'),
                       (ROLE_PRESENCE, 'Video Room Presence Tablet'), (ROLE_BOARD, 'Room Board Screen')],
        ondelete={ROLE_DISPLAY: 'set default', ROLE_CONSOLE: 'set default', ROLE_PRESENCE: 'set default',
                  ROLE_BOARD: 'set default'})
    video_room_ids = fields.One2many('video.room', 'display_node_id', string='Room')
    # Tablets: the room and the restricted (portal) user the tablet is signed in as.
    video_room_id = fields.Many2one('video.room', string='Tablet For Room', ondelete='cascade')
    video_room_board_id = fields.Many2one('video.room.board', string='Shows Board')
    video_tablet_user_id = fields.Many2one(
        'res.users', string='Tablet User', readonly=True, copy=False, ondelete='restrict',
        help='Created with the tablet; no password - the tablet signs in with its rolling key only.')
    # TODO(build), in IoT Interfaces (general "browser Nodes"): pairing from a web page, a JS port of
    #              iot_auth signing (WebCrypto), MAC checks off for these roles, Node -> user sessions.
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

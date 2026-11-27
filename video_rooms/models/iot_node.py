# -*- coding: utf-8 -*-
import uuid

from odoo import _, api, fields, models

ROLE_DISPLAY = 'video_rooms_display'
# Browser Nodes (IoT Interfaces): tablets and PCs that sign in as their own restricted user.
ROLE_CONSOLE = 'video_rooms_console'
ROLE_PRESENCE = 'video_rooms_presence'
ROLE_BOARD = 'video_rooms_board'
BROWSER_ROLES = (ROLE_CONSOLE, ROLE_PRESENCE, ROLE_BOARD)
HOMES = {ROLE_CONSOLE: '/video_rooms/console', ROLE_PRESENCE: '/video_rooms/presence',
         ROLE_BOARD: '/video_rooms/board'}


class IotNode(models.Model):
    """Video Rooms' Node roles: the Room Display (the PC behind the screens) and the
    Console, Presence and Room Board browser Nodes (tablets and PCs)."""
    _inherit = 'iot.node'

    role = fields.Selection(
        selection_add=[(ROLE_DISPLAY, 'Video Room Display'), (ROLE_CONSOLE, 'Video Room Console Tablet'),
                       (ROLE_PRESENCE, 'Video Room Door Tablet'), (ROLE_BOARD, 'Room Board Screen')],
        ondelete={ROLE_DISPLAY: 'set default', ROLE_CONSOLE: 'set default', ROLE_PRESENCE: 'set default',
                  ROLE_BOARD: 'set default'})
    video_display_room_ids = fields.One2many('video.room', 'display_node_id', string='Displays Room')
    video_room_id = fields.Many2one('video.room', string='Tablet For Room', ondelete='cascade', index=True)
    video_room_board_id = fields.Many2one('video.room.board', string='Shows Board', ondelete='cascade')
    # Reported by the Room Display on each sync.
    video_room_state = fields.Json(string='Display State', readonly=True, copy=False,
                                   help='Call state, mic/camera/share, devices and screens the Display reports.')
    video_room_outputs = fields.Json(string='Video Outputs', readonly=True, copy=False,
                                     help='The video outputs the Display found (e.g. HDMI-1, DP-1).')

    @api.model
    def _iot_browser_roles(self):
        return super()._iot_browser_roles() | set(BROWSER_ROLES)

    def _iot_browser_home(self):
        self.ensure_one()
        return HOMES.get(self.role) or super()._iot_browser_home()

    @api.model
    def _video_rooms_create_browser_node(self, role, name, room=None, board=None):
        """A tablet / board screen: its own portal user (no password: it signs in with
        its rolling key only) and its browser Node."""
        group = self.env.ref('video_rooms.group_video_rooms_tablet')
        company = (room or board).company_id
        user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': name,
            'login': 'video-rooms-%s' % uuid.uuid4().hex[:12],
            'company_id': company.id,
            'company_ids': [(6, 0, company.ids)],
            'group_ids': [(6, 0, [group.id])],
        })
        return self.sudo().create({
            'name': name,
            'role': role,
            'company_id': company.id,
            'session_user_id': user.id,
            'video_room_id': room.id if room else False,
            'video_room_board_id': board.id if board else False,
            'location_note': room.name if room else (board.name if board else False),
            'key_rotate_days': 30,
        })

    def unlink(self):
        users = self.sudo().filtered(lambda n: n.role in BROWSER_ROLES).session_user_id
        result = super().unlink()
        # The tablet's own user goes with it.
        users.filtered(lambda u: u.login.startswith('video-rooms-')).sudo().write({'active': False})
        return result

    def _video_room(self):
        """The room this Node serves (display or tablet), sudo."""
        self.ensure_one()
        node = self.sudo()
        if node.role == ROLE_DISPLAY:
            return node.video_display_room_ids[:1]
        return node.video_room_id


class IotProgram(models.Model):
    _inherit = 'iot.program'

    @api.model
    def _iot_builtin_programs(self):
        programs = super()._iot_builtin_programs()
        programs[ROLE_DISPLAY] = {
            'name': 'Video Room Display',
            'description': _('Runs meetings full screen on the room\'s screens in a managed Chrome with the Video '
                             'Rooms extension, and carries out commands from the Room Console.'),
            'folder': 'video_rooms/node_programs/video_rooms_display',
        }
        return programs

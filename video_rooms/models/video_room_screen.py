# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Screens come straight from the room PC's own outputs. More screens will need video wall
# controllers, and the model and Display code are extended when that happens (DESIGN.md §5).
MAX_SCREENS = 4
WALL_GRID = {'front': (4, 2), 'left': (3, 2), 'right': (3, 2), 'back': (4, 2)}


class VideoRoomScreen(models.Model):
    """One screen the Room Display drives, and where it sits (DESIGN.md §5). Set up
    in the Room Designer's Screens tab."""
    _name = 'video.room.screen'
    _description = 'Video Room Screen'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='e.g. "Front Left", "Back Wall".')
    output = fields.Char(help="The room PC's video output, e.g. HDMI-1 (chosen from the outputs the Display reports).")
    # Technical: the Display's layout code depends on these values.
    wall = fields.Selection([('front', 'Front'), ('left', 'Left'), ('right', 'Right'), ('back', 'Back')],
                            required=True, default='front')
    grid_x = fields.Integer(string='Column')
    grid_y = fields.Integer(string='Row')
    grid_w = fields.Integer(string='Width', default=1)
    grid_h = fields.Integer(string='Height', default=1)
    # Technical: what the Display puts on the screen.
    content = fields.Selection([
        ('call', 'Call'),                  # Call screens on one wall are spanned as one canvas
        ('mirror', 'Mirror'),              # exact copy of mirror_of_id
        ('shared', 'Shared Content'),      # companion instance pinned to the share
        ('info', 'Room Info'),             # idle screen / clock / next booking
    ], string='Shows', required=True, default='call')
    mirror_of_id = fields.Many2one('video.room.screen', string='Mirror Of', ondelete='set null',
                                   domain="[('room_id', '=', room_id), ('id', '!=', id)]")
    tv_address = fields.Char(string='TV Address',
                             help='For TVs switched over the LAN: the TV\'s address and port, e.g. 192.168.1.50:9761. '
                                  'For RS-232: the serial device if not the first adapter, e.g. /dev/ttyUSB1.')
    number = fields.Integer(compute='_compute_number', help='The number Identify Screens shows.')

    @api.depends('room_id.screen_ids', 'sequence')
    def _compute_number(self):
        for screen in self:
            screens = screen.room_id.screen_ids.sorted(lambda s: (s.sequence, s.id))
            screen.number = (screens.ids.index(screen.id) + 1) if screen.id in screens.ids else 0

    @api.constrains('room_id')
    def _check_max_screens(self):
        for room in self.room_id:
            if len(room.screen_ids) > MAX_SCREENS:
                raise ValidationError(_(
                    'A room can have up to %s screens, driven by the room PC\'s own outputs. '
                    'More screens need video wall controllers, which are not supported yet.', MAX_SCREENS))

    @api.constrains('wall', 'grid_x', 'grid_y', 'grid_w', 'grid_h')
    def _check_grid(self):
        for screen in self:
            cols, rows = WALL_GRID[screen.wall]
            if (screen.grid_x < 0 or screen.grid_y < 0 or screen.grid_w < 1 or screen.grid_h < 1
                    or screen.grid_x + screen.grid_w > cols or screen.grid_y + screen.grid_h > rows):
                raise ValidationError(_('%(screen)s doesn\'t fit on the %(wall)s wall (%(cols)s × %(rows)s cells).',
                                        screen=screen.name, wall=screen.wall, cols=cols, rows=rows))

    @api.constrains('mirror_of_id', 'content')
    def _check_mirror(self):
        for screen in self.filtered(lambda s: s.content == 'mirror' and s.mirror_of_id):
            if screen.mirror_of_id.room_id != screen.room_id or screen.mirror_of_id == screen:
                raise ValidationError(_('%s can only mirror another screen in the same room.', screen.name))

    def _display_payload(self):
        self.ensure_one()
        return {'id': self.id, 'number': self.number, 'name': self.name, 'output': self.output or '',
                'wall': self.wall, 'x': self.grid_x, 'y': self.grid_y, 'w': self.grid_w, 'h': self.grid_h,
                'content': self.content, 'mirror_of': self.mirror_of_id.id or False,
                'tv_address': self.tv_address or ''}

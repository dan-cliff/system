# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Screens come straight from the room PC's own outputs. More screens will need video wall
# controllers, and the model and Display code are extended when that happens (DESIGN.md §5).
MAX_SCREENS = 4


class VideoRoomScreen(models.Model):
    """One screen the Room Display drives, and where it sits (DESIGN.md §5). Set up
    in the Room Designer's Screens tab; any number per room."""
    _name = 'video.room.screen'
    _description = 'Video Room Screen'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='e.g. "Front Left", "Back Wall".')
    output = fields.Char(help="The room PC's video output, e.g. HDMI-1 (chosen from the outputs the Node reports).")
    # Position, for the layout picture and to span neighbouring screens.
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
    mirror_of_id = fields.Many2one('video.room.screen', string='Mirror Of',
                                   domain="[('room_id', '=', room_id), ('id', '!=', id)]")
    # TODO(build): TV control (HDMI-CEC / RS-232 / IP) as an option model + its connection details.

    @api.constrains('room_id')
    def _check_max_screens(self):
        for room in self.room_id:
            if len(room.screen_ids) > MAX_SCREENS:
                raise ValidationError(_(
                    'A room can have up to %s screens, driven by the room PC\'s own outputs. '
                    'More screens need video wall controllers, which are not supported yet.', MAX_SCREENS))

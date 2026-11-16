# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoom(models.Model):
    """A meeting room: a Room Display (IoT Node behind the TV wall) and one or
    more Room Consoles (tablets). Primary model: gets the Organisation fields
    from org_structure automatically."""
    _name = 'video.room'
    _description = 'Video Room'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    display_node_id = fields.Many2one(
        'iot.node', string='Room Display', domain="[('role', '=', 'video_rooms_display')]", tracking=True,
        help='The PC behind the TV wall, paired in IoT Interfaces.')
    call_display_name = fields.Char(
        string='Name in Calls', help='The name the room joins meetings with, e.g. "Cliff\'s Country Crafts - Board Room".')
    call_email = fields.Char(string='Email for Calls', help='Given when a platform asks for one (e.g. Webex).')
    join_with_mic = fields.Boolean(string='Mic On When Joining', default=True)
    join_with_camera = fields.Boolean(string='Camera On When Joining', default=True)
    auto_join = fields.Boolean(help='Join scheduled calls at their start time without a tap on the console.')
    share_code = fields.Char(readonly=True, copy=False, help='Shown on the TVs for wireless sharing.')
    call_ids = fields.One2many('video.room.call', 'room_id', string='Calls')
    meeting_ids = fields.One2many('meeting.meeting', 'video_room_id', string='Bookings')
    capacity = fields.Integer(help='Seats, shown on the Presence screen.')

    # ── Presence and Do Not Disturb ───────────────────────────────────────
    # Technical: what the Presence screens show, computed from the bookings,
    # the call and Do Not Disturb.
    availability = fields.Selection([
        ('available', 'Available'), ('soon', 'Booked Soon'), ('in_use', 'In Use'), ('dnd', 'Do Not Disturb'),
    ], compute='_compute_availability')
    dnd_active = fields.Boolean(string='Do Not Disturb', tracking=True,
                                help='Set from the Room Console: the door shows that only emergencies may '
                                     'interrupt.')
    dnd_until = fields.Datetime(string='Do Not Disturb Until', tracking=True,
                                help='Empty: until the booking or call ends.')
    dnd_message = fields.Char(string='Do Not Disturb Message', help='Optional, e.g. "Interview in progress".')
    dnd_on_join = fields.Boolean(string='Do Not Disturb During Calls',
                                 help='Switch Do Not Disturb on automatically while the room is in a call.')
    book_now_durations = fields.Char(default='15,30,60',
                                     help='Minutes offered by Book Now on the Presence screen.')
    soon_minutes = fields.Integer(default=10, help='Show "Booked Soon" this many minutes before a booking.')
    # TODO(build): state (idle / in_call / offline) computed from the Node and the current call;
    #              current_call_id; mail alias for invite emails; console users / PIN (see DESIGN.md Q13).

    def _compute_availability(self):
        # TODO(build): dnd -> in_use (current booking or call) -> soon -> available.
        for room in self:
            room.availability = 'dnd' if room.dnd_active else 'available'

    def action_set_dnd(self, active, minutes=None, message=None):
        """From the Room Console. Pushes the change to the Presence screens and the
        Display's idle screen over the bus; cleared automatically at dnd_until, at the
        end of the booking or call, or by the Console."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    def action_book_now(self, minutes):
        """From the Presence screen: a meeting.meeting from now for `minutes`, cut short
        at the next booking; refused if the room is in use."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    def action_send_command(self, command, **params):
        """Queue a command for the Room Display (see video.room.command)."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Who may see the credentials for joining an external meeting.
# TODO(build): replace with the Video Rooms "Allowed" groups for Calls (see security/README.md).
CREDENTIAL_GROUPS = 'base.group_user'


class MeetingMeeting(models.Model):
    """Room booking: a Meeting Management meeting books a Video Room for its
    time, and holds what the room needs to join an external meeting. The
    Presence screens show the booking; only the Room Display is sent the
    credentials, when it joins."""
    _inherit = 'meeting.meeting'

    video_room_id = fields.Many2one('video.room', string='Room', tracking=True, index=True,
                                    help='Books the room for the meeting time. Double bookings are refused.')
    video_instant = fields.Boolean(string='Booked at the Door', readonly=True,
                                   help='Booked with Book Now on the Presence screen.')
    video_checked_in = fields.Datetime(string='Checked In', readonly=True,
                                       help='TODO(build): release the room if nobody checks in (DESIGN.md Q17).')
    video_private = fields.Boolean(string='Private', help='Presence screens show "Booked" instead of the title.')

    # ── Joining an external meeting ───────────────────────────────────────
    video_join_url = fields.Char(string='External Meeting Link', groups=CREDENTIAL_GROUPS, tracking=True,
                                 help='The link the customer sent (Teams, Zoom, Meet, Webex, ...). '
                                      'Our own Teams meetings use the Teams Join URL instead.')
    video_platform_id = fields.Many2one('video.room.platform', string='Platform',
                                        compute='_compute_video_platform_id', store=True, readonly=False)
    video_meeting_code = fields.Char(string='Meeting ID', groups=CREDENTIAL_GROUPS,
                                     help='For joining without a link, e.g. a Zoom or Teams meeting ID or a Meet code.')
    video_passcode = fields.Char(string='Passcode', groups=CREDENTIAL_GROUPS)
    video_host_note = fields.Char(string='Joining Notes', groups=CREDENTIAL_GROUPS,
                                  help='e.g. "Webex site acme.webex.com", "PIN 1234#", "Ask Sam to admit us".')
    video_account_id = fields.Many2one(
        'video.room.account', string='Sign In As', groups=CREDENTIAL_GROUPS,
        domain="[('room_id', 'in', [video_room_id, False]), ('platform_id', '=', video_platform_id)]",
        help='Only when the host only lets signed-in users in: the room account the Display uses.')
    video_call_ids = fields.One2many('video.room.call', 'meeting_id', string='Room Calls')

    @api.depends('video_join_url', 'teams_join_url')
    def _compute_video_platform_id(self):
        Platform = self.env['video.room.platform']
        for meeting in self.sudo():
            meeting.video_platform_id = Platform._detect(meeting.video_join_url or meeting.teams_join_url)

    # TODO(build): @api.constrains no overlap per room (state not cancelled); set `location` to the
    #              room name; create the video.room.call at start (auto_join) or on the Console's Join.

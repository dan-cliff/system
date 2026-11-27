# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ADMIN = 'video_rooms.group_video_rooms_admin'


class MeetingMeeting(models.Model):
    """Room booking: any Meeting Management meeting can book a Video Room for its
    time, and hold what the room needs to join an external meeting.

    The joining details (link, meeting ID, passcode, notes) are kept in fields only
    Video Rooms administrators can read; the booking's organiser (its chairperson's
    user, or whoever created it) sees and edits them through the computed fields
    below. Door screens and Room Boards never get them; the Room Display gets them
    only in the join command (DESIGN.md §6b)."""
    _inherit = 'meeting.meeting'

    video_room_id = fields.Many2one('video.room', string='Room', tracking=True, index=True,
                                    help='Books the room for the meeting time. Double bookings are refused.')
    video_instant = fields.Boolean(string='Booked at the Door', readonly=True, copy=False)
    video_checked_in = fields.Datetime(string='Checked In', readonly=True, copy=False)
    video_private = fields.Boolean(string='Private',
                                   help='Door screens and Room Boards show "Booked" instead of the title.')

    # ── Joining details: stored for administrators only ──────────────────
    video_secret_url = fields.Char(groups=ADMIN, copy=False)
    video_secret_code = fields.Char(groups=ADMIN, copy=False)
    video_secret_passcode = fields.Char(groups=ADMIN, copy=False)
    video_secret_note = fields.Char(groups=ADMIN, copy=False)

    # ── ... shown to the organiser and administrators ───────────────────
    video_join_url = fields.Char(
        string='External Meeting Link', compute='_compute_video_join', inverse='_inverse_video_join',
        help='The link the customer sent (Teams, Zoom, Google Meet, Webex, Odoo Discuss or Jitsi). '
             'Only the organiser and Video Rooms administrators can see it.')
    video_meeting_code = fields.Char(string='Meeting ID', compute='_compute_video_join',
                                     inverse='_inverse_video_join',
                                     help='For an invite with an ID instead of a link (e.g. a Zoom or Teams '
                                          'meeting ID, or a Meet code).')
    video_passcode = fields.Char(string='Passcode', compute='_compute_video_join', inverse='_inverse_video_join')
    video_join_note = fields.Char(string='Joining Notes', compute='_compute_video_join',
                                  inverse='_inverse_video_join',
                                  help='e.g. "Webex site acme.webex.com", "PIN 1234#", "Ask Sam to admit us".')
    video_can_see_details = fields.Boolean(compute='_compute_video_join')
    video_has_details = fields.Boolean(string='Has Joining Details', compute='_compute_video_has_details',
                                       store=True, compute_sudo=True)
    video_platform_id = fields.Many2one('video.room.platform', string='Platform', compute='_compute_video_platform',
                                        store=True, compute_sudo=True, readonly=False)
    video_account_id = fields.Many2one(
        'video.room.account', string='Sign In As',
        domain="[('platform_id', '=', video_platform_id), '|', ('room_id', '=', False), ('room_id', '=', video_room_id)]",
        help='Only for hosts that refuse guests: the room account to join with (signed in on the Room Display).')
    video_call_ids = fields.One2many('video.room.call', 'meeting_id', string='Room Calls')

    # ── Joining details ──────────────────────────────────────────────────
    def _video_can_see(self):
        self.ensure_one()
        user = self.env.user
        return bool(self.env.su or user.has_group(ADMIN) or not self.id
                    or self.sudo().create_uid == user
                    or (self.sudo().chairperson_id and self.sudo().chairperson_id == user.partner_id))

    @api.depends_context('uid')
    @api.depends('video_has_details')
    def _compute_video_join(self):
        for meeting in self:
            visible = meeting._video_can_see()
            secret = meeting.sudo()
            meeting.video_can_see_details = visible
            meeting.video_join_url = secret.video_secret_url if visible else False
            meeting.video_meeting_code = secret.video_secret_code if visible else False
            meeting.video_passcode = secret.video_secret_passcode if visible else False
            meeting.video_join_note = secret.video_secret_note if visible else False

    def _inverse_video_join(self):
        for meeting in self:
            if not meeting._video_can_see():
                raise UserError(_('Only the organiser and Video Rooms administrators can change the joining '
                                  'details of "%s".', meeting.name))
            meeting.sudo().write({
                'video_secret_url': (meeting.video_join_url or '').strip() or False,
                'video_secret_code': (meeting.video_meeting_code or '').strip() or False,
                'video_secret_passcode': (meeting.video_passcode or '').strip() or False,
                'video_secret_note': (meeting.video_join_note or '').strip() or False,
            })

    @api.depends('video_secret_url', 'video_secret_code', 'teams_join_url')
    def _compute_video_has_details(self):
        for meeting in self:
            meeting.video_has_details = bool(meeting.video_secret_url or meeting.video_secret_code
                                             or meeting.teams_join_url)

    @api.depends('video_secret_url', 'teams_join_url')
    def _compute_video_platform(self):
        Platform = self.env['video.room.platform'].sudo()
        for meeting in self:
            url = meeting.video_secret_url or meeting.teams_join_url
            if url:
                meeting.video_platform_id = Platform._detect(url)
            elif not meeting.video_platform_id:
                meeting.video_platform_id = False

    def _video_join_url(self):
        """The link the room joins with (sudo): the external link, one built from the
        meeting ID and passcode, or the meeting's own Teams link."""
        self.ensure_one()
        meeting = self.sudo()
        if meeting.video_secret_url:
            return meeting.video_secret_url
        if meeting.video_secret_code and meeting.video_platform_id:
            url = meeting.video_platform_id._build_join_url(meeting.video_secret_code,
                                                            meeting.video_secret_passcode)
            if url:
                return url
        return meeting.teams_join_url or ''

    # ── Booking rules ────────────────────────────────────────────────────
    @api.onchange('video_room_id')
    def _onchange_video_room_id(self):
        if self.video_room_id:
            self.location = self.video_room_id.name

    @api.constrains('video_room_id', 'date_start', 'date_end', 'duration', 'state')
    def _check_video_room_free(self):
        Room = self.env['video.room']
        for meeting in self.sudo().filtered(lambda m: m.video_room_id and m.state != 'cancelled'):
            start, end = meeting.date_start, Room._meeting_end(meeting)
            if end <= start:
                raise ValidationError(_('"%s" ends before it starts.', meeting.name))
            others = self.sudo().search([
                ('video_room_id', '=', meeting.video_room_id.id), ('id', '!=', meeting.id),
                ('state', '!=', 'cancelled'), ('date_start', '<', end),
                ('date_start', '>=', start - timedelta(days=2)),
            ])
            clash = others.filtered(lambda o: Room._meeting_end(o) > start)[:1]
            if clash:
                room = meeting.video_room_id
                raise ValidationError(_(
                    '%(room)s is already booked from %(start)s to %(end)s by "%(other)s".',
                    room=room.name, start=room._local_time(clash.date_start, '%d/%m/%Y %H:%M'),
                    end=room._local_time(Room._meeting_end(clash), '%H:%M'), other=clash.name))

    def action_video_join(self):
        """Join this booking's external meeting in its room (Control Rooms)."""
        self.ensure_one()
        if not self.video_room_id:
            raise UserError(_('Choose a Room first.'))
        self.video_room_id._check_control()
        self.video_room_id._join_meeting(self)
        return self.video_room_id._notify(_('%s is joining the call…', self.video_room_id.name))

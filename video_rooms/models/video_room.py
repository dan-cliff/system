# -*- coding: utf-8 -*-
import logging
import secrets
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Do Not Disturb never lasts longer than this (decided, DESIGN.md §11).
DND_MAX = timedelta(hours=4)
# A booking with no end time holds the room this long.
DEFAULT_BOOKING = timedelta(hours=1)
# Book Now refuses slots shorter than this.
MIN_BOOK_NOW = timedelta(minutes=5)
# Call states in which the room is busy with a call.
ACTIVE_CALL_STATES = ('joining', 'lobby', 'in_call')


class VideoRoom(models.Model):
    """A meeting room: a Room Display (the PC behind its screens, an IoT Node),
    Console and Presence tablets (browser Nodes), its screens and layouts.
    Bookings are Meeting Management meetings with this room."""
    _name = 'video.room'
    _description = 'Video Room'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Colour Index')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 tracking=True)
    capacity = fields.Integer(string='Seats', help='Shown at the door and on Room Boards.')
    note = fields.Html(string='Notes')

    # ── Devices ──────────────────────────────────────────────────────────
    display_node_id = fields.Many2one(
        'iot.node', string='Room Display', tracking=True, copy=False,
        domain="[('role', '=', 'video_rooms_display')]",
        help='The PC behind the room\'s screens, paired in IoT Interfaces.')
    display_online = fields.Boolean(related='display_node_id.is_online', string='Display Online')
    display_state = fields.Json(related='display_node_id.video_room_state', string='Display State')
    tablet_node_ids = fields.One2many('iot.node', 'video_room_id', string='Tablets')
    tablet_count = fields.Integer(compute='_compute_counts')
    tv_control_id = fields.Many2one('video.room.tv.control', string='TV Power Control',
                                    help='How the room\'s TVs are switched on and off.')

    # ── Joining calls ────────────────────────────────────────────────────
    call_display_name = fields.Char(
        string='Name in Calls',
        help='The name the room joins meetings with, e.g. "Cliff\'s Country Crafts - Board Room". '
             'Empty: the room\'s name.')
    call_email = fields.Char(string='Email for Calls', help='Given when a platform asks for one (e.g. Webex).')
    join_with_mic = fields.Boolean(string='Mic On When Joining', default=True)
    join_with_camera = fields.Boolean(string='Camera On When Joining', default=True)
    share_code = fields.Char(readonly=True, copy=False,
                             help='Shown on the screens: laptops type it to share wirelessly.')

    # ── Bookings and calls ───────────────────────────────────────────────
    meeting_ids = fields.One2many('meeting.meeting', 'video_room_id', string='Bookings')
    call_ids = fields.One2many('video.room.call', 'room_id', string='Calls')
    meeting_count = fields.Integer(compute='_compute_counts')
    call_count = fields.Integer(compute='_compute_counts')
    current_meeting_id = fields.Many2one('meeting.meeting', compute='_compute_schedule', string='Current Booking')
    next_meeting_id = fields.Many2one('meeting.meeting', compute='_compute_schedule', string='Next Booking')
    current_call_id = fields.Many2one('video.room.call', compute='_compute_schedule', string='Current Call')
    # Technical: what the screens and boards show (code branches on it).
    availability = fields.Selection([
        ('available', 'Available'), ('soon', 'Booked Soon'), ('in_use', 'In Use'), ('dnd', 'Do Not Disturb'),
    ], compute='_compute_schedule')
    checkin_required = fields.Boolean(
        string='Require Check-In', tracking=True,
        help='Release a booking nobody checks in to (on the Console or at the door) in time.')
    checkin_minutes = fields.Integer(string='Check In Within (minutes)', default=10)
    book_now_durations = fields.Char(string='Book Now Options (minutes)', default='15,30,60',
                                     help='Minutes offered by Book Now at the door, separated by commas.')
    soon_minutes = fields.Integer(string='"Booked Soon" From (minutes)', default=10,
                                  help='Show "Booked Soon" this many minutes before a booking.')

    # ── Do Not Disturb ───────────────────────────────────────────────────
    dnd_active = fields.Boolean(string='Do Not Disturb', tracking=True, copy=False,
                                help='Set from the Room Console: the door shows that only emergencies may '
                                     'interrupt.')
    dnd_until = fields.Datetime(string='Do Not Disturb Until', tracking=True, copy=False,
                                help='It never lasts more than 4 hours.')
    dnd_message = fields.Char(string='Do Not Disturb Message', copy=False,
                              help='Optional, e.g. "Interview in progress".')
    dnd_auto = fields.Boolean(copy=False, help='Technical: switched on automatically for a call.')
    dnd_on_join = fields.Boolean(string='Do Not Disturb During Calls',
                                 help='Switch Do Not Disturb on automatically while the room is in a call.')

    # ── Room Designer (DESIGN.md §5, §6e) ─────────────────────────────────
    screen_ids = fields.One2many('video.room.screen', 'room_id', string='Screens', copy=True)
    console_layout = fields.Json(copy=True,
                                 help='Console tiles for the call and idle pages, as saved by the Room Designer.')
    console_template_id = fields.Many2one('video.room.layout.template', domain="[('kind', '=', 'console')]",
                                          help='Follow this template; empty: the room keeps its own layout.')
    presence_layout = fields.Json(copy=True, help='Presence screen blocks and theme, as saved by the Room Designer.')
    presence_template_id = fields.Many2one('video.room.layout.template', domain="[('kind', '=', 'presence')]")
    admin_pin = fields.Char(string='Console Admin PIN', groups='video_rooms.group_video_rooms_admin', copy=False,
                            help="Opens the Console's setup mode. Everything else on the Console needs no PIN.")

    _check_minutes = models.Constraint(
        'CHECK(checkin_minutes >= 1 AND soon_minutes >= 0)',
        'Check-in and "Booked Soon" minutes must be positive.')

    # ── Computes ─────────────────────────────────────────────────────────
    def _compute_counts(self):
        for room in self:
            room.meeting_count = len(room.sudo().meeting_ids)
            room.call_count = len(room.sudo().call_ids)
            room.tablet_count = len(room.sudo().tablet_node_ids)

    @api.model
    def _meeting_end(self, meeting):
        return meeting.date_end or (meeting.date_start + (timedelta(hours=meeting.duration) if meeting.duration
                                                          else DEFAULT_BOOKING))

    def _bookings(self, start, end):
        """This room's bookings overlapping [start, end), in order (sudo)."""
        self.ensure_one()
        meetings = self.env['meeting.meeting'].sudo().search([
            ('video_room_id', '=', self.id), ('state', '!=', 'cancelled'),
            ('date_start', '<', end), ('date_start', '>=', start - timedelta(days=1)),
        ], order='date_start')
        return meetings.filtered(lambda m: self._meeting_end(m) > start)

    @api.depends('meeting_ids.date_start', 'meeting_ids.date_end', 'meeting_ids.state', 'call_ids.state',
                 'dnd_active', 'dnd_until', 'soon_minutes')
    def _compute_schedule(self):
        now = fields.Datetime.now()
        for room in self:
            today = room._bookings(now, now + timedelta(hours=24))
            current = today.filtered(lambda m: m.date_start <= now)[:1]
            upcoming = today.filtered(lambda m: m.date_start > now)[:1]
            call = room.sudo().call_ids.filtered(lambda c: c.state in ACTIVE_CALL_STATES)[:1]
            room.current_meeting_id = current
            room.next_meeting_id = upcoming
            room.current_call_id = call
            if room._dnd_is_on(now):
                room.availability = 'dnd'
            elif current or call:
                room.availability = 'in_use'
            elif upcoming and upcoming.date_start <= now + timedelta(minutes=room.soon_minutes):
                room.availability = 'soon'
            else:
                room.availability = 'available'

    def _refresh_schedule(self):
        """Recompute availability now (it also depends on the time of day)."""
        self.invalidate_recordset(['current_meeting_id', 'next_meeting_id', 'current_call_id', 'availability'])

    def _dnd_is_on(self, now=None):
        self.ensure_one()
        now = now or fields.Datetime.now()
        return bool(self.dnd_active and (not self.dnd_until or self.dnd_until > now))

    def _call_name(self):
        self.ensure_one()
        return self.call_display_name or self.name

    # ── CRUD ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('share_code', self._new_share_code())
        return super().create(vals_list)

    @api.model
    def _new_share_code(self):
        return '%06d' % secrets.randbelow(1000000)

    @api.constrains('display_node_id')
    def _check_display_node(self):
        for room in self.filtered('display_node_id'):
            other = self.search([('display_node_id', '=', room.display_node_id.id), ('id', '!=', room.id)], limit=1)
            if other:
                raise ValidationError(_('%(node)s is already the Room Display of %(room)s.',
                                        node=room.display_node_id.name, room=other.name))

    @api.constrains('book_now_durations')
    def _check_book_now_durations(self):
        for room in self:
            try:
                room._book_now_options()
            except ValueError:
                raise ValidationError(_('Book Now options are minutes separated by commas, e.g. 15,30,60.'))

    def _book_now_options(self):
        self.ensure_one()
        values = [int(v) for v in (self.book_now_durations or '').replace(' ', '').split(',') if v]
        if any(v <= 0 for v in values):
            raise ValueError('minutes must be positive')
        return values or [15, 30, 60]

    # ── Do Not Disturb, Book Now, check-in ──────────────────────────────
    def action_set_dnd(self, active=True, minutes=None, message=None, auto=False):
        """Switch Do Not Disturb on or off (the Console, or a call when Do Not Disturb
        During Calls is on). It lasts until the current booking or call ends, for
        ``minutes``, or until switched off - never more than 4 hours."""
        now = fields.Datetime.now()
        for room in self.sudo():
            if not active:
                room.write({'dnd_active': False, 'dnd_until': False, 'dnd_message': False, 'dnd_auto': False})
                continue
            until = now + DND_MAX
            if minutes:
                until = min(until, now + timedelta(minutes=int(minutes)))
            elif room.current_meeting_id:
                until = min(until, self._meeting_end(room.current_meeting_id))
            room.write({'dnd_active': True, 'dnd_until': until, 'dnd_auto': auto,
                        'dnd_message': (message or '').strip()[:80] or False})
        return True

    def action_dnd_on(self):
        return self.action_set_dnd(True)

    def action_dnd_off(self):
        return self.action_set_dnd(False)

    def action_book_now(self, minutes):
        """Book the room from now (the Presence screen's Book Now): ends at the next
        booking at the latest. Refused while the room is in use."""
        self.ensure_one()
        room = self.sudo()
        room._refresh_schedule()
        now = fields.Datetime.now().replace(second=0, microsecond=0)
        if room.availability in ('in_use', 'dnd'):
            raise UserError(_('%s is in use.', room.name))
        end = now + timedelta(minutes=int(minutes))
        if room.next_meeting_id and room.next_meeting_id.date_start < end:
            end = room.next_meeting_id.date_start
        if end - now < MIN_BOOK_NOW:
            raise UserError(_('%s is booked from %s: there isn\'t time to book it now.',
                              room.name, room._local_time(room.next_meeting_id.date_start)))
        meeting = self.env['meeting.meeting'].sudo().create({
            'name': _('Booked at the door'),
            'date_start': now,
            'date_end': end,
            'video_room_id': room.id,
            'video_instant': True,
            'video_checked_in': now,
            'state': 'scheduled',
            'location': room.name,
        })
        return meeting

    def action_check_in(self):
        """Check in to the current booking (or one starting within "Booked Soon")."""
        self.ensure_one()
        room = self.sudo()
        now = fields.Datetime.now()
        meeting = room.current_meeting_id or (
            room.next_meeting_id if room.next_meeting_id and
            room.next_meeting_id.date_start <= now + timedelta(minutes=room.soon_minutes) else False)
        if not meeting:
            raise UserError(_('%s has no booking to check in to.', room.name))
        if not meeting.video_checked_in:
            meeting.video_checked_in = now
        return meeting

    def action_end_booking(self):
        """End the current booking now (frees the room)."""
        self.ensure_one()
        room = self.sudo()
        meeting = room.current_meeting_id
        if not meeting:
            raise UserError(_('%s has no booking running.', room.name))
        meeting.write({'date_end': fields.Datetime.now()})
        if room.dnd_active:
            room.action_set_dnd(False)
        return meeting

    @api.model
    def _cron_housekeeping(self):
        """Every minute: end Do Not Disturb that ran out and release bookings nobody
        checked in to (rooms with Require Check-In)."""
        now = fields.Datetime.now()
        self.sudo().search([('dnd_active', '=', True), ('dnd_until', '<=', now)]).action_set_dnd(False)
        for room in self.sudo().search([('checkin_required', '=', True)]):
            late = now - timedelta(minutes=room.checkin_minutes)
            for meeting in room._bookings(late - timedelta(hours=12), now):
                if (meeting.date_start <= late and not meeting.video_checked_in and not meeting.video_instant
                        and not room.current_call_id):
                    meeting.write({'video_room_id': False})
                    meeting.message_post(body=_('%(room)s released: nobody checked in within %(min)s minutes.',
                                                room=room.name, min=room.checkin_minutes))
                    room.message_post(body=_('Released "%(meeting)s": nobody checked in within %(min)s minutes.',
                                             meeting=meeting.name, min=room.checkin_minutes))

    # ── Commands to the Room Display ────────────────────────────────────
    def _send_command(self, command, **params):
        """Queue a command for the Room Display (collected on its next sync)."""
        self.ensure_one()
        if not self.sudo().display_node_id:
            raise UserError(_('%s has no Room Display yet: pair one in its Devices tab.', self.name))
        return self.env['video.room.command'].sudo().create({
            'room_id': self.id, 'command': command, 'params': params or {},
            'call_id': params.get('call_id') or False,
        })

    def _check_control(self):
        if not self.env.su and not self.env.user.has_group('video_rooms.group_video_rooms_control'):
            raise UserError(_('Controlling rooms needs the "Video Rooms: Control Rooms" permission.'))

    def _join(self, url, meeting=None, source_xmlid='video_rooms.call_source_console', account=None):
        """Join a meeting at ``url`` (credentials included): creates the call and the
        join command. Returns the call."""
        self.ensure_one()
        room = self.sudo()
        if not url:
            raise UserError(_('There is no meeting link to join.'))
        platform = self.env['video.room.platform'].sudo()._detect(url)
        if not platform:
            raise UserError(_('This link isn\'t from a supported platform (Teams, Zoom, Google Meet, Webex, '
                              'Odoo Discuss or Jitsi).'))
        if room.current_call_id:
            raise UserError(_('%s is already in a call: leave it first.', room.name))
        source = self.env.ref(source_xmlid, raise_if_not_found=False)
        call = self.env['video.room.call'].sudo().create({
            'name': meeting.name if meeting else _('Call from %s', room.name),
            'room_id': room.id,
            'meeting_id': meeting.id if meeting else False,
            'url': url,
            'platform_id': platform.id,
            'source_id': source.id if source else False,
            'organiser_partner_id': meeting.chairperson_id.id if meeting else False,
            'state': 'joining',
        })
        room._send_command(
            'join', call_id=call.id, url=url, driver=platform.driver, display_name=room._call_name(),
            email=room.call_email or '', mic=room.join_with_mic, camera=room.join_with_camera,
            account=(account.login or account.name) if account else '')
        if meeting and not meeting.video_checked_in:
            meeting.video_checked_in = fields.Datetime.now()
        if room.dnd_on_join and not room.dnd_active:
            room.action_set_dnd(True, auto=True)
        room.share_code = self._new_share_code()
        return call

    def _join_meeting(self, meeting):
        self.ensure_one()
        meeting = meeting.sudo()
        if meeting.video_room_id != self:
            raise UserError(_('That booking is not for %s.', self.name))
        return self._join(meeting._video_join_url(), meeting=meeting,
                          source_xmlid='video_rooms.call_source_booking', account=meeting.video_account_id)

    def _join_link(self, url=None, platform=None, code=None, passcode=None):
        """Ad-hoc join from the Console: a pasted link, or a platform + meeting ID + passcode."""
        self.ensure_one()
        if not url and platform and code:
            url = self.env['video.room.platform'].sudo().browse(int(platform))._build_join_url(code, passcode)
        return self._join((url or '').strip())

    def action_join_current(self):
        """Join the current booking's external meeting (from Odoo: Control Rooms)."""
        self._check_control()
        self.ensure_one()
        if not self.current_meeting_id:
            raise UserError(_('%s has no booking running.', self.name))
        self._join_meeting(self.current_meeting_id)
        return self._notify(_('Joining the call…'))

    def _control(self, command, **params):
        """Send an in-call command (mic, camera, share, layout, volume, leave, ...)."""
        self.ensure_one()
        call = self.sudo().current_call_id
        if command == 'leave':
            if call:
                call.write({'state': 'done', 'left_at': fields.Datetime.now()})
            if self.dnd_auto:
                self.action_set_dnd(False)
        return self._send_command(command, call_id=call.id if call else False, **params)

    def action_leave(self):
        self._check_control()
        self.ensure_one()
        self._control('leave')
        return self._notify(_('Leaving the call.'))

    def action_identify_screens(self):
        """Show a big number on each screen for a few seconds."""
        self.ensure_one()
        if not (self.env.user.has_group('video_rooms.group_video_rooms_design')
                or self.env.user.has_group('video_rooms.group_video_rooms_control')):
            raise UserError(_('Identifying screens needs Control Rooms or Design Rooms.'))
        self._send_command('identify', seconds=8)
        return self._notify(_('Showing numbers on %s\'s screens.', self.name))

    def action_restart_display(self):
        self._check_control()
        self.ensure_one()
        self._send_command('restart_browser')
        return self._notify(_('Restarting the Room Display\'s browser.'))

    def _notify(self, message, kind='success'):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': kind, 'message': message}}

    # ── Tablets ──────────────────────────────────────────────────────────
    def _add_tablet(self, role, label):
        self.ensure_one()
        if not self.env.user.has_group('video_rooms.group_video_rooms_admin'):
            raise UserError(_('Only Video Rooms administrators can add tablets.'))
        node = self.env['iot.node']._video_rooms_create_browser_node(
            role, '%s - %s' % (self.name, label), room=self)
        return node.action_pair()

    def action_add_console_tablet(self):
        return self._add_tablet('video_rooms_console', _('Console'))

    def action_add_presence_tablet(self):
        return self._add_tablet('video_rooms_presence', _('Door'))

    def action_add_display(self):
        """Create the Room Display Node and show its install command."""
        self.ensure_one()
        if not self.env.user.has_group('video_rooms.group_video_rooms_admin'):
            raise UserError(_('Only Video Rooms administrators can add a Room Display.'))
        if self.display_node_id:
            return self.display_node_id.action_pair()
        node = self.env['iot.node'].sudo().create({
            'name': '%s - %s' % (self.name, _('Display')), 'role': 'video_rooms_display',
            'company_id': self.company_id.id, 'location_note': self.name,
        })
        self.display_node_id = node
        return node.action_pair()

    # ── Navigation ───────────────────────────────────────────────────────
    def action_open_designer(self):
        self.ensure_one()
        if not self.env.user.has_group('video_rooms.group_video_rooms_design'):
            raise UserError(_('The Room Designer needs the "Video Rooms: Design Rooms" permission.'))
        return {'type': 'ir.actions.client', 'tag': 'video_rooms.room_designer', 'name': _('Room Designer'),
                'params': {'room_id': self.id}, 'context': {'active_id': self.id}}

    def action_view_bookings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('video_rooms.action_video_room_bookings')
        action['domain'] = [('video_room_id', '=', self.id)]
        action['context'] = {'default_video_room_id': self.id, 'default_location': self.name}
        return action

    def action_view_calls(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('video_rooms.action_video_room_call')
        action['domain'] = [('room_id', '=', self.id)]
        action['context'] = {'default_room_id': self.id}
        return action

    def action_view_tablets(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Tablets'), 'res_model': 'iot.node',
                'view_mode': 'list,form', 'domain': [('video_room_id', '=', self.id)],
                'context': {'default_video_room_id': self.id}}

    # ── What the tablets, boards and Display read ───────────────────────
    def _local_time(self, value, fmt='%H:%M'):
        if not value:
            return ''
        return fields.Datetime.context_timestamp(self.with_context(tz=self._tz()), value).strftime(fmt)

    def _tz(self):
        self.ensure_one()
        return self.env.context.get('tz') or self.company_id.partner_id.tz or self.env.user.tz or 'UTC'

    def _meeting_payload(self, meeting, show_titles=True):
        private = meeting.video_private or not show_titles
        return {
            'id': meeting.id,
            'title': _('Booked') if private else meeting.name,
            'organiser': '' if private else (meeting.chairperson_id.name or meeting.create_uid.name or ''),
            'start': self._local_time(meeting.date_start),
            'end': self._local_time(self._meeting_end(meeting)),
            'start_ts': fields.Datetime.to_string(meeting.date_start),
            'end_ts': fields.Datetime.to_string(self._meeting_end(meeting)),
            'checked_in': bool(meeting.video_checked_in),
            'platform': meeting.video_platform_id.name or '',
            'can_join': bool(meeting.sudo()._video_join_url()),
        }

    def _status_payload(self, show_titles=True):
        """Status for the door, the Room Boards and the Console (never credentials)."""
        self.ensure_one()
        room = self.sudo()
        room._refresh_schedule()
        now = fields.Datetime.now()
        today = room._bookings(now.replace(hour=0, minute=0, second=0), now + timedelta(hours=24))
        tz_now = fields.Datetime.context_timestamp(room.with_context(tz=room._tz()), now)
        current = room.current_meeting_id
        call = room.current_call_id
        return {
            'id': room.id,
            'name': room.name,
            'capacity': room.capacity,
            'availability': room.availability,
            'now': tz_now.strftime('%H:%M'),
            'date': tz_now.strftime('%a %d/%m/%Y'),
            'current': room._meeting_payload(current, show_titles) if current else False,
            'next': room._meeting_payload(room.next_meeting_id, show_titles) if room.next_meeting_id else False,
            'today': [room._meeting_payload(m, show_titles) for m in today],
            'minutes_left': int((room._meeting_end(current) - now).total_seconds() // 60) if current else 0,
            'dnd': {'active': room._dnd_is_on(now), 'until': room._local_time(room.dnd_until),
                    'message': room.dnd_message or ''},
            'call': {'state': call.state, 'platform': call.platform_id.name or ''} if call else False,
            'book_now': room._book_now_options() if room.availability in ('available', 'soon') else [],
            'checkin': {'required': room.checkin_required, 'minutes': room.checkin_minutes},
            'display_online': room.display_online,
        }

    def _console_payload(self):
        """Everything the Room Console shows (no credentials: the Display gets them)."""
        self.ensure_one()
        room = self.sudo()
        state = room.display_state or {}
        payload = room._status_payload()
        payload.update({
            'layout': room._effective_layout('console'),
            'display': {
                'online': room.display_online,
                'mic': state.get('mic'), 'camera': state.get('camera'), 'sharing': state.get('sharing'),
                'volume': state.get('volume'), 'call_state': state.get('call_state'),
                'error': state.get('error') or '', 'share_code': room.share_code,
                'hdmi': bool(state.get('hdmi_present')),
            },
            'platforms': [{'id': p.id, 'name': p.name, 'by_id': bool(p.join_url_template)}
                          for p in self.env['video.room.platform'].sudo().search([])],
            'has_pin': bool(room.admin_pin),
            'controls': room._console_controls(),
        })
        return payload

    def _console_controls(self):
        """Room device controls for the Console (Home Assistant adds its own)."""
        return []

    def _console_device(self, params):
        """A room device control used on the Console (Home Assistant handles these)."""
        raise UserError(_('%s has no device controls.', self.name))

    def _presence_payload(self):
        self.ensure_one()
        room = self.sudo()
        layout = room._effective_layout('presence')
        payload = room._status_payload(show_titles=(layout.get('privacy') != 'booked'))
        payload['layout'] = layout
        return payload

    def _effective_layout(self, kind):
        """The room's layout for 'console' or 'presence' (its template's when it follows one)."""
        self.ensure_one()
        template = self.console_template_id if kind == 'console' else self.presence_template_id
        layout = (template.layout if template else None) or (
            self.console_layout if kind == 'console' else self.presence_layout)
        return layout or self._default_layout(kind)

    @api.model
    def _default_layout(self, kind):
        if kind == 'console':
            def tile(t, x, y, w=1, h=1):
                return {'id': uuid.uuid4().hex[:8], 'type': t, 'x': x, 'y': y, 'w': w, 'h': h}
            return {
                'cols': 6, 'rows': 4,
                'call': [tile('mic', 0, 0, 2, 2), tile('camera', 2, 0, 2, 2), tile('leave', 4, 0, 2, 2),
                         tile('volume', 0, 2, 3, 1), tile('share', 3, 2, 3, 1), tile('dnd', 0, 3, 3, 1),
                         tile('layout', 3, 3, 3, 1)],
                'idle': [tile('join', 0, 0, 4, 3), tile('dnd', 4, 0, 2, 1), tile('share', 4, 1, 2, 1),
                         tile('tv', 4, 2, 2, 1), tile('volume', 0, 3, 6, 1)],
            }
        return {
            'order': ['name', 'status', 'current', 'timeleft', 'dnd', 'today', 'booknow', 'meta', 'clock'],
            'show': {'name': 1, 'status': 1, 'current': 1, 'timeleft': 1, 'dnd': 1, 'today': 1, 'booknow': 1,
                     'meta': 1, 'clock': 1},
            'theme': 'dark', 'orient': 'landscape', 'privacy': 'title',
            'colors': {'available': '#0FA585', 'soon': '#F08A00', 'in_use': '#E8455B', 'dnd': '#7A4BE0'},
        }

    def _display_payload(self):
        """Settings the Room Display needs on each sync."""
        self.ensure_one()
        room = self.sudo()
        return {
            'room': room.name,
            'call_name': room._call_name(),
            'share_code': room.share_code,
            'screens': [s._display_payload() for s in room.screen_ids],
            'tv_control': {'method': room.tv_control_id.method or 'none',
                           'on': room.tv_control_id.on_command or '', 'off': room.tv_control_id.off_command or ''},
            'status': room._status_payload(),
        }

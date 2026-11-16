# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestVideoRooms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Room = cls.env['video.room']
        cls.Meeting = cls.env['meeting.meeting']
        cls.room = cls.Room.create({'name': 'Board Room', 'capacity': 12, 'checkin_required': True})
        cls.now = fields.Datetime.now().replace(second=0, microsecond=0)

    def _meeting(self, start_offset, minutes=60, **vals):
        start = self.now + timedelta(minutes=start_offset)
        return self.Meeting.create(dict({
            'name': 'Supplier review', 'date_start': start, 'date_end': start + timedelta(minutes=minutes),
            'video_room_id': self.room.id, 'state': 'scheduled',
        }, **vals))

    def test_platform_detection_and_links(self):
        Platform = self.env['video.room.platform']
        self.assertEqual(Platform._detect('https://teams.microsoft.com/l/meetup-join/19%3a/0?context=x').driver, 'teams')
        self.assertEqual(Platform._detect('https://us02web.zoom.us/j/8123?pwd=x').driver, 'zoom')
        self.assertEqual(Platform._detect('https://meet.google.com/abc-defg-hij').driver, 'google_meet')
        self.assertEqual(Platform._detect('https://acme.webex.com/meet/sam').driver, 'webex')
        self.assertEqual(Platform._detect('https://meet.jit.si/OurRoom').driver, 'jitsi')
        self.assertFalse(Platform._detect('https://example.com/meeting'))
        zoom = self.env.ref('video_rooms.platform_zoom')
        self.assertEqual(zoom._build_join_url('812 3456 7890', 'abc'), 'https://app.zoom.us/wc/join/81234567890?pwd=abc')

    def test_no_double_booking(self):
        self._meeting(60)
        with self.assertRaises(ValidationError):
            self._meeting(90)
        # Back to back is fine, and cancelled meetings don't count.
        self._meeting(120)
        self._meeting(90, state='cancelled')

    def test_availability_and_book_now(self):
        self.assertEqual(self.room.availability, 'available')
        self._meeting(3, 30)
        self.room.invalidate_recordset()
        self.assertEqual(self.room.availability, 'soon')
        # Book Now stops at the next booking, and refuses when there is no time.
        with self.assertRaises(UserError):
            self.room.action_book_now(15)
        other = self.Room.create({'name': 'Pod A'})
        booking = other.action_book_now(30)
        self.assertTrue(booking.video_instant and booking.video_checked_in)
        other.invalidate_recordset()
        self.assertEqual(other.availability, 'in_use')
        with self.assertRaises(UserError):
            other.action_book_now(15)
        other.action_end_booking()
        other.invalidate_recordset()
        self.assertEqual(other.availability, 'available')

    def test_do_not_disturb(self):
        self.room.action_set_dnd(True, message='Interview in progress')
        self.assertEqual(self.room.availability, 'dnd')
        self.assertLessEqual(self.room.dnd_until, fields.Datetime.now() + timedelta(hours=4, minutes=1))
        # It ends with the booking when there is one, and never runs past 4 hours.
        meeting = self._meeting(-10, 30)
        self.room.action_set_dnd(True)
        self.assertEqual(self.room.dnd_until, meeting.date_end)
        self.room.action_set_dnd(True, minutes=600)
        self.assertLessEqual(self.room.dnd_until, fields.Datetime.now() + timedelta(hours=4, minutes=1))
        self.room.dnd_until = fields.Datetime.now() - timedelta(minutes=1)
        self.Room._cron_housekeeping()
        self.assertFalse(self.room.dnd_active)

    def test_check_in_release(self):
        meeting = self._meeting(-15, 60)
        self.Room._cron_housekeeping()
        self.assertFalse(meeting.video_room_id, 'nobody checked in within 10 minutes: released')
        kept = self._meeting(-15, 60, name='Checked in')
        kept.video_checked_in = fields.Datetime.now()
        self.Room._cron_housekeeping()
        self.assertEqual(kept.video_room_id, self.room)

    def test_credentials_only_for_organiser_and_admins(self):
        organiser = new_test_user(self.env, 'organiser', groups='base.group_user,meeting_management.group_meeting_user')
        colleague = new_test_user(self.env, 'colleague', groups='base.group_user,meeting_management.group_meeting_user')
        meeting = self.Meeting.with_user(organiser).create({
            'name': 'Customer call', 'date_start': self.now + timedelta(hours=3),
            'date_end': self.now + timedelta(hours=4), 'video_room_id': self.room.id,
            'video_join_url': 'https://meet.google.com/abc-defg-hij', 'video_passcode': '1234',
        })
        self.assertEqual(meeting.video_join_url, 'https://meet.google.com/abc-defg-hij')
        self.assertEqual(meeting.video_platform_id, self.env.ref('video_rooms.platform_google_meet'))
        as_colleague = meeting.with_user(colleague)
        self.assertFalse(as_colleague.video_can_see_details)
        self.assertFalse(as_colleague.video_join_url)
        self.assertTrue(as_colleague.video_has_details)
        with self.assertRaises(UserError):
            as_colleague.video_passcode = '9999'
        # Door screens never get them.
        payload = self.room._presence_payload()
        self.assertNotIn('meet.google.com', str(payload))

    def test_join_and_display_flow(self):
        with self.assertRaises(UserError):
            self.room._join('https://meet.google.com/abc-defg-hij')  # no Room Display yet
        node = self.env['iot.node'].create({'name': 'Board Room Display', 'role': 'video_rooms_display'})
        self.room.display_node_id = node
        meeting = self._meeting(-5, 60, video_secret_url='https://teams.microsoft.com/meet/123?p=abc')
        call = self.room._join_meeting(meeting)
        self.assertEqual(call.state, 'joining')
        self.assertTrue(meeting.video_checked_in)
        commands = self.env['video.room.command']._collect(self.room)
        self.assertEqual(commands[0]['command'], 'join')
        self.assertEqual(commands[0]['params']['url'], 'https://teams.microsoft.com/meet/123?p=abc')
        self.assertEqual(commands[0]['params']['driver'], 'teams')
        call._report_state('in_call')
        self.assertEqual(call.state, 'in_call')
        self.assertTrue(call.joined_at)
        with self.assertRaises(UserError):
            self.room._join('https://meet.google.com/abc-defg-hij')  # already in a call
        self.room._control('leave')
        self.assertEqual(call.state, 'done')

    def test_screens_limit(self):
        for i in range(4):
            self.env['video.room.screen'].create({'room_id': self.room.id, 'name': 'Screen %s' % i, 'wall': 'front',
                                                  'grid_x': i, 'grid_y': 0})
        with self.assertRaises(ValidationError):
            self.env['video.room.screen'].create({'room_id': self.room.id, 'name': 'Fifth', 'wall': 'back'})
        with self.assertRaises(ValidationError):
            self.room.screen_ids[0].grid_x = 4  # off the wall

    def test_board(self):
        other = self.Room.create({'name': 'Pod A'})
        board = self.env['video.room.board'].create({'name': 'Head Office', 'room_ids': [(6, 0, [self.room.id, other.id])],
                                                     'sort_by': 'name'})
        payload = board._payload()
        self.assertEqual([r['name'] for r in payload['rooms']], ['Board Room', 'Pod A'])
        board.write({'room_selection': 'rule', 'room_domain': "[('name', '=', 'Pod A')]"})
        self.assertEqual([r['name'] for r in board._payload()['rooms']], ['Pod A'])
        overview = self.env['video.room.board'].get_overview(board.id)
        self.assertEqual(overview['board']['name'], 'Head Office')

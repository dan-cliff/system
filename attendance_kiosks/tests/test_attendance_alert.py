from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .test_attendance_kiosk import AttendanceKioskCase


@tagged('post_install', '-at_install')
class TestAttendanceAlerts(AttendanceKioskCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['res.users'].create({
            'name': 'Mia Manager', 'login': 'mia.alerts', 'email': 'mia@example.com',
            'group_ids': [Command.link(cls.env.ref('hr_attendance.group_hr_attendance_officer').id)],
            'tz': 'UTC',
        })
        cls.alice.tz = 'UTC'
        cls.bob.tz = 'UTC'
        cls.channel = cls.env['discuss.channel'].create({'name': 'Arrivals', 'channel_type': 'channel'})
        cls.odoobot = cls.env.ref('base.partner_root')

    def make_alert(self, events, employees=None, **vals):
        return self.env['attendance.alert'].create({
            'name': 'Test alert',
            'requester_id': self.manager.id,
            'employee_ids': [Command.set((employees or self.alice).ids)],
            'condition_ids': [Command.create({'event': event}) for event in events],
            'recurrence': 'recurring',
            **vals,
        })

    def sent(self, alert):
        return alert.log_ids.mapped('event')

    def chat_messages(self):
        chat = self.env['discuss.channel'].search([
            ('channel_type', '=', 'chat'),
            ('channel_member_ids.partner_id', '=', self.manager.partner_id.id),
        ])
        return chat.message_ids.filtered(lambda m: m.author_id == self.odoobot)

    def test_first_sign_in_today_messages_requester(self):
        alert = self.make_alert(['in_first_today'])
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        self.assertEqual(self.sent(alert), ['in_first_today'])
        messages = self.chat_messages()
        self.assertEqual(len(messages), 1)
        self.assertIn('Alice Able', messages.body)
        self.assertIn('Front Door', messages.body)
        # A second sign in the same day is not the first.
        self.kiosk._kiosk_sign_out(self.alice, now - timedelta(hours=1))
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(minutes=30), [])
        self.assertEqual(len(alert.log_ids), 1)

    def test_every_sign_in_and_out(self):
        alert = self.make_alert(['in_every', 'out_every'])
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=3), [])
        self.kiosk._kiosk_sign_out(self.alice, now - timedelta(hours=2))
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=1), [])
        self.assertEqual(sorted(self.sent(alert)), ['in_every', 'in_every', 'out_every'])

    def test_first_sign_out_today(self):
        alert = self.make_alert(['out_first_today'])
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=3), [])
        self.kiosk._kiosk_sign_out(self.alice, now - timedelta(hours=2))
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=1), [])
        self.kiosk._kiosk_sign_out(self.alice, now - timedelta(minutes=30))
        self.assertEqual(self.sent(alert), ['out_first_today'])

    def test_site_conditions(self):
        alert = self.make_alert(['in_first_site', 'in_first_site_today', 'out_first_site_today'])
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=4), [])
        # First ever at the Workshop: matches the first condition only (one message per sign in).
        self.assertEqual(self.sent(alert), ['in_first_site'])
        # Moving to the Yard: signs out of the Workshop and in at the Yard.
        self.kiosk_yard._kiosk_sign_in(self.alice, now - timedelta(hours=3), [])
        self.assertEqual(sorted(self.sent(alert)), ['in_first_site', 'in_first_site', 'out_first_site_today'])
        # Back at the Workshop later today: not the first time there, not first today.
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        self.assertEqual(len(alert.log_ids), 4)  # only the Yard sign out fires
        self.assertEqual(alert.log_ids.sorted('id')[-1].event, 'out_first_site_today')

    def test_site_filter(self):
        alert = self.make_alert(['in_every'])
        alert.condition_ids.location_ids = self.yard
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        self.assertFalse(alert.log_ids)
        self.kiosk_yard._kiosk_sign_in(self.alice, now - timedelta(hours=1), [])
        self.assertEqual(alert.log_ids.work_location_id, self.yard)

    def test_once_off_archives(self):
        alert = self.make_alert(['in_every'], recurrence='once')
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        self.assertFalse(alert.active)
        self.assertTrue(alert.last_triggered)
        self.kiosk._kiosk_sign_out(self.alice, now - timedelta(hours=1))
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(minutes=30), [])
        self.assertEqual(len(alert.log_ids), 1)

    def test_only_watched_employees(self):
        alert = self.make_alert(['in_every'])
        self.kiosk._kiosk_sign_in(self.bob, fields.Datetime.now(), [])
        self.assertFalse(alert.log_ids)

    def test_post_to_channel_for_everyone(self):
        alert = self.make_alert(['in_every', 'out_every'], employees=self.alice, all_employees=True,
                                notify_requester=False, channel_ids=[Command.set(self.channel.ids)])
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.bob, now - timedelta(hours=1), [])
        self.kiosk._kiosk_sign_out(self.bob, now)
        posts = self.channel.message_ids.filtered(lambda m: m.author_id == self.odoobot)
        self.assertEqual(len(posts), 2)
        self.assertTrue(any('signed out' in p.body for p in posts))
        self.assertFalse(self.chat_messages(), 'The requester asked not to be messaged')
        self.assertEqual(len(alert.log_ids), 2)

    def test_schedule_window(self):
        now = fields.Datetime.now()
        weekday = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now.weekday()]
        alert = self.make_alert(['in_every'], **{weekday: False})
        self.kiosk._kiosk_sign_in(self.alice, now, [])
        self.assertFalse(alert.log_ids, 'Not on this weekday')
        alert.write({weekday: True, 'date_start': now.date() + timedelta(days=1)})
        self.kiosk._kiosk_sign_out(self.alice, now)
        self.kiosk._kiosk_sign_in(self.alice, now, [])
        self.assertFalse(alert.log_ids, 'Not started yet')

    def test_backdated_entries_do_not_alert(self):
        alert = self.make_alert(['in_every'])
        old = fields.Datetime.now() - timedelta(days=3)
        self.env['hr.attendance'].create({
            'employee_id': self.alice.id, 'check_in': old, 'check_out': old + timedelta(hours=8),
        })
        self.assertFalse(alert.log_ids)

    def test_systray_style_check_in_out(self):
        alert = self.make_alert(['in_every', 'out_every'])
        attendance = self.env['hr.attendance'].create({'employee_id': self.alice.id, 'check_in': fields.Datetime.now()})
        attendance.write({'check_out': fields.Datetime.now()})
        self.assertEqual(sorted(self.sent(alert)), ['in_every', 'out_every'])
        self.assertEqual(alert.log_ids.work_location_id, attendance.employee_id.work_location_id)

    def test_company_aware(self):
        other = self.env['res.company'].create({'name': 'Other Co'})
        outsider = self.env['hr.employee'].create({'name': 'Out Sider', 'company_id': other.id, 'tz': 'UTC'})
        alert = self.make_alert(['in_every'], all_employees=True)
        self.env['hr.attendance'].create({'employee_id': outsider.id, 'check_in': fields.Datetime.now()})
        self.assertFalse(alert.log_ids, "Another company's employees do not trigger this company's alerts")
        self.assertEqual(alert.company_id, self.env.company)

    def test_officer_sees_only_own_alerts(self):
        mine = self.make_alert(['in_every'])
        theirs = self.make_alert(['in_every'], requester_id=self.env.user.id)
        visible = self.env['attendance.alert'].with_user(self.manager).search([])
        self.assertIn(mine, visible)
        self.assertNotIn(theirs, visible)

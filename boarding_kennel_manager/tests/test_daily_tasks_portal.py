import base64
from datetime import date, datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.addons.boarding_kennel_manager import access_levels

PIXEL_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
DAY = date(2026, 10, 2)


class KennelTaskCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'UTC'
        cls.env.company.kennel_invoicing = False  # food is typed in, not picked from inventory
        cls.env.company.kennel_observation_times = '09:00, 16:00'
        ref = lambda xmlid: cls.env.ref(f'boarding_kennel_manager.{xmlid}')
        cls.dog = ref('kennel_species_dog')
        cls.twice_daily = ref('kennel_frequency_twice_daily')
        cls.once_daily = ref('kennel_frequency_once_daily')
        cls.ate_all = ref('kennel_feed_consumption_all')
        cls.refused = ref('kennel_feed_consumption_none')
        cls.given = ref('kennel_dose_outcome_given')
        cls.health_concern = ref('kennel_observation_type_health_concern')
        cls.smith = cls.env['res.partner'].create({'name': 'Test Smith', 'email': 'smith@example.com'})
        cls.jones = cls.env['res.partner'].create({'name': 'Test Jones', 'email': 'jones@example.com'})
        cls.diet = cls.env['kennel.diet'].create({
            'name': 'Dry', 'food': '1 cup Biscuits', 'frequency_id': cls.twice_daily.id,
        })
        cls.rex = cls.env['kennel.resident'].create({
            'name': 'Rex', 'partner_id': cls.smith.id, 'species_id': cls.dog.id, 'default_diet_id': cls.diet.id,
        })
        cls.tom = cls.env['kennel.resident'].create({'name': 'Tom', 'partner_id': cls.jones.id})
        cls.keeper = new_test_user(cls.env, login='task_keeper', groups='base.group_user,boarding_kennel_manager.group_kennel_booking_create,boarding_kennel_manager.group_kennel_booking_update,boarding_kennel_manager.group_kennel_resident_create,boarding_kennel_manager.group_kennel_resident_update,boarding_kennel_manager.group_kennel_task_create,boarding_kennel_manager.group_kennel_task_update,boarding_kennel_manager.group_kennel_medication_create,boarding_kennel_manager.group_kennel_medication_update,boarding_kennel_manager.group_kennel_medication_delete,boarding_kennel_manager.group_kennel_observation_create,boarding_kennel_manager.group_kennel_observation_update,boarding_kennel_manager.group_kennel_yard_view')

    def _checked_in_booking(self, resident, arrival=datetime(2026, 10, 1, 9), departure=datetime(2026, 10, 5, 17), **vals):
        booking = self.env['kennel.booking'].create({
            'partner_id': resident.partner_id.id, 'resident_ids': [Command.set(resident.ids)],
            'arrival_datetime': arrival, 'departure_datetime': departure, **vals,
        })
        booking.write({'state': 'checked_in', 'checked_in_datetime': arrival})
        return booking

    def _generate(self, booking, day=DAY):
        return self.env['kennel.task']._generate_for_bookings(booking, day=day)


@tagged('post_install', '-at_install')
class TestDailyTasks(KennelTaskCommon):

    def test_frequency_times(self):
        self.assertEqual(self.twice_daily._get_times(), [(8, 0), (17, 0)])
        with self.assertRaises(ValidationError):
            self.twice_daily.times = '8am'
        with self.assertRaises(ValidationError):
            self.env.company.kennel_observation_times = '25:00'

    def test_daily_list_for_a_full_day(self):
        booking = self._checked_in_booking(self.rex, medication_ids=[Command.create({
            'resident_id': self.rex.id, 'name': 'Apoquel', 'dose': '1 tablet', 'frequency_id': self.once_daily.id,
        })])
        tasks = self._generate(booking)
        self.assertEqual(sorted(tasks.mapped('task_type')), ['feed', 'feed', 'medication', 'observation', 'observation'])
        self.assertEqual(
            sorted(t.scheduled_datetime.strftime('%H:%M') for t in tasks.filtered(lambda t: t.task_type == 'feed')),
            ['08:00', '17:00'])
        self.assertTrue(all(task.date == DAY and task.resident_id == self.rex for task in tasks))
        feed = tasks.filtered(lambda t: t.task_type == 'feed')[:1]
        self.assertEqual(feed.quantity_given, '1 cup Biscuits')
        self.assertEqual(feed.food, '1 cup Biscuits')
        self.assertIn('1 cup Biscuits', feed.instructions)
        # Running it again adds nothing.
        self.assertFalse(self._generate(booking))

    def test_only_times_during_the_stay(self):
        booking = self._checked_in_booking(self.rex, arrival=datetime(2026, 10, 2, 12), departure=datetime(2026, 10, 3, 10))
        first_day = self._generate(booking)
        self.assertEqual(sorted(t.scheduled_datetime.strftime('%H:%M') for t in first_day), ['16:00', '17:00'])
        last_day = self._generate(booking, day=date(2026, 10, 3))
        self.assertEqual(sorted(t.scheduled_datetime.strftime('%H:%M') for t in last_day), ['08:00', '09:00'])

    def test_company_timezone(self):
        self.env.company.partner_id.tz = 'Australia/Melbourne'  # AEST (UTC+10) in early September
        booking = self._checked_in_booking(self.rex, arrival=datetime(2026, 9, 1), departure=datetime(2026, 9, 10))
        feeds = self._generate(booking, day=date(2026, 9, 5)).filtered(lambda t: t.task_type == 'feed')
        # 08:00 and 17:00 in Melbourne (AEST, UTC+10).
        self.assertEqual(sorted(t.scheduled_datetime.strftime('%d %H:%M') for t in feeds), ['04 22:00', '05 07:00'])

    def test_complete_feed_logs_on_the_animal(self):
        booking = self._checked_in_booking(self.rex)
        feed = self._generate(booking).filtered(lambda t: t.task_type == 'feed')[:1]
        feed = feed.with_user(self.keeper)
        with self.assertRaises(UserError):
            feed.action_complete()
        feed.consumption_id = self.refused
        feed.notes = 'Sniffed it and walked off.'
        feed.photo_ids = [Command.create({
            'name': 'rex.png', 'datas': PIXEL_PNG, 'res_model': 'kennel.task', 'res_id': feed.id,
        })]
        action = feed.action_complete()
        # The form closes and goes back to the list.
        self.assertEqual(action, {'type': 'ir.actions.client', 'tag': 'kennel_back_to_list'})
        self.assertEqual(feed.state, 'done')
        self.assertEqual(feed.done_by_id, self.keeper)
        self.assertTrue(feed.problem)
        message = feed.message_id
        self.assertEqual((message.model, message.res_id), ('kennel.resident', self.rex.id))
        self.assertEqual(message.subtype_id, self.env.ref('boarding_kennel_manager.mt_kennel_care'))
        self.assertFalse(message.subtype_id.internal)
        self.assertIn('Refused', message.body)
        self.assertIn('Sniffed it', message.body)
        photo = message.attachment_ids
        self.assertEqual(len(photo), 1)
        self.assertEqual((photo.res_model, photo.res_id), ('kennel.resident', self.rex.id))
        self.assertTrue(photo.access_token)
        self.assertEqual(self.rex.care_count, 1)
        with self.assertRaises(UserError):
            feed.action_complete()
        with self.assertRaises(UserError):
            feed.action_reopen()

    def test_complete_medication_and_observation(self):
        booking = self._checked_in_booking(self.rex, medication_ids=[Command.create({
            'resident_id': self.rex.id, 'name': 'Apoquel', 'dose': '1 tablet', 'frequency_id': self.once_daily.id,
        })])
        tasks = self._generate(booking).with_user(self.keeper)
        dose = tasks.filtered(lambda t: t.task_type == 'medication')
        self.assertEqual(dose.dose_given, '1 tablet')
        dose.outcome_id = self.given
        dose.action_complete()
        self.assertEqual(dose.administration_id.medication_id, booking.medication_ids)
        self.assertEqual(dose.administration_id.user_id, self.keeper)
        self.assertEqual(booking.medication_ids.last_given_datetime, dose.administration_id.administered_datetime)

        observation = tasks.filtered(lambda t: t.task_type == 'observation')[:1]
        with self.assertRaises(UserError):
            observation.action_complete()
        observation.observation_type_id = self.health_concern
        self.assertTrue(observation.concern)
        observation.summary = 'Limping on the left front leg'
        observation.action_complete()
        self.assertEqual(observation.observation_id.summary, 'Limping on the left front leg')
        self.assertTrue(observation.observation_id.concern)
        self.assertEqual(booking.concern_count, 1)

    def test_not_required_and_reopen(self):
        booking = self._checked_in_booking(self.rex)
        task = self._generate(booking)[:1].with_user(self.keeper)
        task.action_not_required()
        self.assertEqual(task.state, 'cancelled')
        task.action_reopen()
        self.assertEqual(task.state, 'todo')

    def test_check_in_and_out(self):
        booking = self.env['kennel.booking'].create({
            'partner_id': self.smith.id, 'resident_ids': [Command.set(self.rex.ids)],
            'arrival_datetime': datetime(2020, 1, 1), 'departure_datetime': datetime(2099, 1, 1),
        })
        booking.action_confirm()
        booking.action_check_in()
        self.assertEqual(len(booking.task_ids), 4)  # today: 2 feeds + 2 observation rounds
        self.assertEqual(booking.task_todo_count, 4)
        booking.action_check_out()
        self.assertEqual(set(booking.task_ids.mapped('state')), {'cancelled'})

    def test_schedule_changes_update_the_list(self):
        booking = self._checked_in_booking(self.rex, arrival=datetime(2020, 1, 1), departure=datetime(2099, 1, 1))
        self.env['kennel.task']._generate_for_bookings(booking)
        feeds = lambda: booking.task_ids.filtered(lambda t: t.task_type == 'feed' and t.state == 'todo')
        self.assertEqual(len(feeds()), 2)
        booking.line_ids.frequency_id = self.once_daily
        self.assertEqual(len(feeds()), 1)
        # New medication for a checked-in animal goes straight onto today's list.
        booking.medication_ids = [Command.create({
            'resident_id': self.rex.id, 'name': 'Drops', 'frequency_id': self.twice_daily.id,
        })]
        self.assertEqual(len(booking.task_ids.filtered(lambda t: t.task_type == 'medication')), 2)
        booking.medication_ids.frequency_id = self.once_daily
        self.assertEqual(len(booking.task_ids.filtered(lambda t: t.task_type == 'medication')), 1)
        # Medication that hasn't started yet isn't on today's list.
        booking.medication_ids.start_date = date(2098, 1, 1)
        self.assertFalse(booking.task_ids.filtered(lambda t: t.task_type == 'medication'))

    def test_cron(self):
        booking = self._checked_in_booking(self.rex, arrival=datetime(2020, 1, 1), departure=datetime(2099, 1, 1))
        self.env['kennel.task']._cron_generate_tasks()
        self.assertEqual(len(booking.task_ids), 4)
        self.env['kennel.task']._cron_generate_tasks()
        self.assertEqual(len(booking.task_ids), 4)

    def test_customer_follows_but_is_not_emailed_about_care(self):
        booking = self._checked_in_booking(self.rex)
        self.assertIn(self.smith, self.rex.message_partner_ids)
        self.assertIn(self.smith, booking.message_partner_ids)
        follower = self.rex.message_follower_ids.filtered(lambda f: f.partner_id == self.smith)
        self.assertNotIn(self.env.ref('boarding_kennel_manager.mt_kennel_care'), follower.subtype_ids)


@tagged('post_install', '-at_install')
class TestPortalInvite(KennelTaskCommon):

    def test_invite_needs_the_permission(self):
        with self.assertRaises(AccessError):
            self.smith.with_user(self.keeper).action_kennel_portal_invite()

    @mute_logger('odoo.addons.mail.models.mail_mail')
    def test_customer_portal_user_invites(self):
        inviter = new_test_user(self.env, login='inviter', groups='base.group_user,boarding_kennel_manager.group_kennel_portal_user')
        action = self.smith.with_user(inviter).action_kennel_portal_invite()
        wizard = self.env['portal.wizard'].with_user(inviter).browse(action['res_id'])
        wizard_user = wizard.user_ids.filtered(lambda u: u.partner_id == self.smith)
        wizard_user.email = 'new.smith@example.com'
        wizard_user.action_grant_access()
        self.assertTrue(self.smith.user_ids._is_portal())
        self.assertEqual(self.smith.email, 'new.smith@example.com')
        self.assertIn('boarding_kennel_manager.group_kennel_portal_user',
                      access_levels.ROLE_EXTRA_GROUPS['Administrator'])

    def test_portal_customer_sees_only_their_own(self):
        portal = new_test_user(self.env, login='smith_portal', groups='base.group_portal', partner_id=self.smith.id)
        booking = self._checked_in_booking(self.rex)
        other = self._checked_in_booking(self.tom)
        env = self.env(user=portal)
        self.assertEqual(env['kennel.resident'].search([]), self.rex)
        self.assertEqual(env['kennel.booking'].search([]), booking)
        with self.assertRaises(AccessError):
            env['kennel.booking'].browse(other.id).check_access('read')
        with self.assertRaises(AccessError):
            env['kennel.resident'].browse(self.rex.id).write({'name': 'Hacked'})


@tagged('post_install', '-at_install')
class TestPortalPages(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'UTC'
        cls.env.company.kennel_invoicing = False
        smith = cls.env['res.partner'].create({'name': 'Portal Smith', 'email': 'psmith@example.com'})
        jones = cls.env['res.partner'].create({'name': 'Portal Jones'})
        cls.portal = new_test_user(cls.env, login='psmith', password='psmith-pass-1234', groups='base.group_portal',
                                   partner_id=smith.id)
        cls.rex = cls.env['kennel.resident'].create({'name': 'Rexington', 'partner_id': smith.id,
                                                     'medical_notes': 'Allergic to chicken'})
        cls.tom = cls.env['kennel.resident'].create({'name': 'Tomkins', 'partner_id': jones.id})
        cls.booking = cls.env['kennel.booking'].create({
            'partner_id': smith.id, 'resident_ids': [Command.set(cls.rex.ids)],
            'arrival_datetime': datetime(2026, 10, 1, 9), 'departure_datetime': datetime(2026, 10, 5, 17),
        })
        cls.booking.write({'state': 'checked_in', 'checked_in_datetime': datetime(2026, 10, 1, 9)})
        cls.booking.line_ids.frequency_id = cls.env.ref('boarding_kennel_manager.kennel_frequency_twice_daily')
        task = cls.env['kennel.task']._generate_for_bookings(cls.booking, day=DAY).filtered(
            lambda t: t.task_type == 'feed')[:1]
        task.write({
            'consumption_id': cls.env.ref('boarding_kennel_manager.kennel_feed_consumption_all').id,
            'photo_ids': [Command.create({'name': 'dinner.png', 'datas': PIXEL_PNG})],
        })
        task.action_complete()
        cls.photo = task.message_id.attachment_ids
        assert cls.photo, 'the completed feed should carry its photo'

    def test_pages(self):
        self.authenticate('psmith', 'psmith-pass-1234')
        home = self.url_open('/my/home')
        self.assertIn('My Animals', home.text)
        counters = self.make_jsonrpc_request('/my/counters', {'counters': ['kennel_resident_count', 'kennel_booking_count']})
        self.assertEqual(counters, {'kennel_resident_count': 1, 'kennel_booking_count': 1})

        animals = self.url_open('/my/kennel/animals')
        self.assertIn('Rexington', animals.text)
        self.assertNotIn('Tomkins', animals.text)

        animal = self.url_open(f'/my/kennel/animals/{self.rex.id}')
        self.assertEqual(animal.status_code, 200)
        self.assertIn('Allergic to chicken', animal.text)
        self.assertIn('Care Log', animal.text)
        self.assertIn('Ate All', animal.text)
        self.assertIn(f'/web/image/{self.photo.id}', animal.text)
        self.assertIn('o_portal_chatter', animal.text)

        booking = self.url_open(f'/my/kennel/bookings/{self.booking.id}')
        self.assertEqual(booking.status_code, 200)
        self.assertIn(self.booking.name, booking.text)
        self.assertIn('01/10/2026', booking.text)

        photo = self.url_open(f'/web/image/{self.photo.id}?access_token={self.photo.access_token}')
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo.headers['Content-Type'], 'image/png')

        # Someone else's animal: back to the portal home.
        other = self.url_open(f'/my/kennel/animals/{self.tom.id}', allow_redirects=False)
        self.assertEqual(other.status_code, 303)

    def test_customer_messages_keepers(self):
        self.authenticate('psmith', 'psmith-pass-1234')
        self.make_jsonrpc_request('/mail/message/post', {
            'thread_model': 'kennel.resident', 'thread_id': self.rex.id,
            'post_data': {'body': 'How is Rexington settling in?', 'message_type': 'comment'},
        })
        message = self.rex.message_ids[:1]
        self.assertEqual(message.author_id, self.portal.partner_id)
        self.assertIn('settling in', message.body)
        # The care entry is among the messages the portal chatter shows.
        fetched = self.make_jsonrpc_request('/mail/chatter_fetch', {
            'thread_model': 'kennel.resident', 'thread_id': self.rex.id,
            'token': self.rex._portal_ensure_token(),
        })
        bodies = ' '.join(str(m['body']) for m in fetched['data']['mail.message'])
        self.assertIn('Ate All', bodies)
        self.assertIn('settling in', bodies)

import json
from datetime import datetime, timedelta

from odoo import fields
from odoo.fields import Command
from odoo.tests import HttpCase, new_test_user, tagged

PIXEL_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='


@tagged('post_install', '-at_install')
class TestControlPlane(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.write({'kennel_invoicing': False, 'kennel_cp_theme': 'dark', 'kennel_cp_refresh_minutes': 7})
        company.partner_id.tz = 'UTC'
        cls.keeper = new_test_user(cls.env, login='cp_keeper', password='cp-keeper-pass-1234',
                                   groups='base.group_user,boarding_kennel_manager.group_kennel_booking_create,boarding_kennel_manager.group_kennel_booking_update,boarding_kennel_manager.group_kennel_resident_create,boarding_kennel_manager.group_kennel_resident_update,boarding_kennel_manager.group_kennel_task_create,boarding_kennel_manager.group_kennel_task_update,boarding_kennel_manager.group_kennel_medication_create,boarding_kennel_manager.group_kennel_medication_update,boarding_kennel_manager.group_kennel_medication_delete,boarding_kennel_manager.group_kennel_observation_create,boarding_kennel_manager.group_kennel_observation_update,boarding_kennel_manager.group_kennel_yard_view')
        cls.outsider = new_test_user(cls.env, login='cp_outsider', password='cp-outsider-pass-1234', groups='base.group_user')
        cls.yard = cls.env['kennel.yard'].create({
            'name': 'Run 7', 'code': 'R7', 'capacity': 2,
            'yard_type_id': cls.env.ref('boarding_kennel_manager.kennel_yard_type_kennel').id,
        })
        cls.empty_run = cls.env['kennel.yard'].create({'name': 'Run 8'})
        customer = cls.env['res.partner'].create({'name': 'CP Customer'})
        cls.rex = cls.env['kennel.resident'].create({
            'name': 'Rexy', 'partner_id': customer.id, 'image_1920': PIXEL_PNG,
            'medical_notes': 'Allergic to chicken', 'behaviour_notes': 'Pulls on the lead',
        })
        now = fields.Datetime.now()
        cls.booking = cls.env['kennel.booking'].create({
            'partner_id': customer.id, 'resident_ids': [Command.set(cls.rex.ids)],
            'arrival_datetime': now - timedelta(days=1), 'departure_datetime': now + timedelta(days=2),
        })
        cls.booking.line_ids.write({
            'yard_id': cls.yard.id, 'food': '1 cup biscuits',
            'frequency_id': cls.env.ref('boarding_kennel_manager.kennel_frequency_twice_daily').id,
        })
        cls.booking.write({'state': 'checked_in', 'checked_in_datetime': now - timedelta(days=1)})
        cls.medication = cls.env['kennel.medication'].create({
            'booking_id': cls.booking.id, 'resident_id': cls.rex.id, 'name': 'Apoquel', 'dose': '1 tablet',
        })

    def _data(self, yard):
        return self.make_jsonrpc_request(f'/kennel/control-plane/{yard.id}/data', {})

    def _submit(self, kind, values, yard=None):
        return self.make_jsonrpc_request(f'/kennel/control-plane/{(yard or self.yard).id}/submit',
                                         {'kind': kind, 'values': values})

    def test_page_and_pwa(self):
        self.authenticate('cp_keeper', 'cp-keeper-pass-1234')
        page = self.url_open(f'/kennel/control-plane/{self.yard.id}')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Run 7', page.text)
        self.assertIn('data-theme="dark"', page.text)
        self.assertIn('manifest.webmanifest', page.text)
        manifest = self.url_open(f'/kennel/control-plane/{self.yard.id}/manifest.webmanifest').json()
        self.assertEqual(manifest['start_url'], f'/kennel/control-plane/{self.yard.id}')
        self.assertIn('Run 7', manifest['name'])
        worker = self.url_open('/kennel/control-plane/sw.js')
        self.assertEqual(worker.status_code, 200)
        self.assertIn('javascript', worker.headers['Content-Type'])
        action = self.yard.action_open_control_plane()
        self.assertEqual(action['url'], f'/kennel/control-plane/{self.yard.id}')

    def test_only_keepers(self):
        self.authenticate('cp_outsider', 'cp-outsider-pass-1234')
        self.assertEqual(self.url_open(f'/kennel/control-plane/{self.yard.id}').status_code, 403)

    def test_screen_data(self):
        self.authenticate('cp_keeper', 'cp-keeper-pass-1234')
        data = self._data(self.yard)
        self.assertEqual(data['yard']['name'], 'Run 7')
        self.assertEqual(data['yard']['type'], 'Kennel')
        self.assertEqual(data['yard']['company'], self.env.company.name)
        self.assertEqual(data['theme']['refresh_minutes'], 7)
        [resident] = data['residents']
        self.assertEqual(resident['name'], 'Rexy')
        self.assertTrue(resident['photo_url'])
        self.assertEqual(resident['food'], '1 cup biscuits')
        self.assertEqual(resident['medical'], 'Allergic to chicken')
        self.assertEqual(resident['medication'], ['Apoquel 1 tablet'])
        self.assertRegex(resident['arrival'], r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$')
        # Today's tasks for this yard were built on the way (feeds, observation rounds), with any overdue.
        self.assertTrue(data['tasks'])
        self.assertTrue({'feed', 'observation'} <= {task['type'] for task in data['tasks']})
        vacant = self._data(self.empty_run)
        self.assertEqual(vacant['residents'], [])
        self.assertEqual(vacant['tasks'], [])

    def test_complete_a_task_on_the_screen(self):
        self.authenticate('cp_keeper', 'cp-keeper-pass-1234')
        feed = next(task for task in self._data(self.yard)['tasks'] if task['type'] == 'feed')
        # Missing the required answer: an error, and nothing saved.
        result = self._submit('task', {'task_id': feed['id']})
        self.assertIn('error', result)
        self.assertEqual(self.env['kennel.task'].browse(feed['id']).state, 'todo')
        eaten = self.env.ref('boarding_kennel_manager.kennel_feed_consumption_all')
        result = self._submit('task', {
            'task_id': feed['id'], 'consumption_id': str(eaten.id), 'notes': 'Licked the bowl',
            'photos': [{'name': 'bowl.png', 'data': PIXEL_PNG}],
        })
        self.assertNotIn('error', result)
        task = self.env['kennel.task'].browse(feed['id'])
        self.assertEqual(task.state, 'done')
        self.assertEqual(task.done_by_id, self.keeper)
        self.assertEqual(len(task.message_id.attachment_ids), 1)
        self.assertIn(feed['id'], [done['id'] for done in result['data']['done']])
        # A task from another yard can't be completed here.
        other = self._submit('task', {'task_id': feed['id']}, yard=self.empty_run)
        self.assertIn('error', other)

    def test_care_toolbar_forms(self):
        self.authenticate('cp_keeper', 'cp-keeper-pass-1234')
        rex = str(self.rex.id)
        self.assertNotIn('error', self._submit('observation', {
            'resident_id': rex, 'summary': 'Playing with a ball', 'concern': False}))
        self.assertEqual(self.booking.observation_ids.summary, 'Playing with a ball')

        self.assertNotIn('error', self._submit('medication', {
            'resident_id': rex, 'name': 'Ear drops', 'dose': '2 drops', 'start_date': '01/01/2026', 'end_date': ''}))
        drops = self.booking.medication_ids.filtered(lambda m: m.name == 'Ear drops')
        self.assertEqual(str(drops.start_date), '2026-01-01')
        self.assertIn('error', self._submit('medication', {'resident_id': rex, 'name': 'X', 'start_date': '2026-01-01'}))

        outcome = self.env.ref('boarding_kennel_manager.kennel_dose_outcome_given')
        self.assertNotIn('error', self._submit('dose', {
            'medication_id': str(self.medication.id), 'dose_given': '1 tablet', 'outcome_id': str(outcome.id)}))
        self.assertEqual(self.medication.administration_ids.user_id, self.keeper)

        eaten = self.env.ref('boarding_kennel_manager.kennel_feed_consumption_most')
        result = self._submit('care', {'resident_id': rex, 'task_type': 'feed', 'consumption_id': str(eaten.id),
                                       'quantity_given': 'Treat'})
        self.assertNotIn('error', result)
        extra = self.booking.task_ids.filtered(lambda t: t.state == 'done' and t.quantity_given == 'Treat')
        self.assertTrue(extra.message_id)

        # Animals from other yards can't be picked.
        self.assertIn('error', self._submit('observation', {'resident_id': rex, 'summary': 'x'}, yard=self.empty_run))

    def test_refresh_setting(self):
        settings = self.env['res.config.settings'].create({'kennel_cp_refresh_minutes': 0})
        settings.execute()
        self.assertEqual(self.env.company.kennel_cp_refresh_minutes, 0)
        self.authenticate('cp_keeper', 'cp-keeper-pass-1234')
        page = self.url_open(f'/kennel/control-plane/{self.yard.id}')
        payload = page.text.split('<script id="cp-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(payload)['theme']['refresh_minutes'], 0)

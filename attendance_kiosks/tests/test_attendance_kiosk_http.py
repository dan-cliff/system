import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .test_attendance_kiosk import AttendanceKioskCase


@tagged('post_install', '-at_install')
class TestKioskRoutes(AttendanceKioskCase, HttpCase):

    def post(self, path, data):
        return self.url_open(f'/kiosk/{self.kiosk.access_token}{path}', data=json.dumps(data),
                             headers={'Content-Type': 'application/json'})

    def get(self, path=''):
        return self.url_open(f'/kiosk/{self.kiosk.access_token}{path}')

    def test_app_manifest_and_service_worker(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Front Door', response.text)
        manifest = self.get('/manifest.webmanifest').json()
        self.assertEqual(manifest['start_url'], f'/kiosk/{self.kiosk.access_token}')
        sw = self.get('/sw.js')
        self.assertEqual(sw.headers['Service-Worker-Allowed'], f'/kiosk/{self.kiosk.access_token}')
        self.assertIn(f"'/kiosk/{self.kiosk.access_token}'", sw.text)
        self.assertEqual(self.url_open('/kiosk/not-a-real-token-123456').status_code, 404)

    def test_config_and_roster(self):
        config = self.get('/config.json').json()
        self.assertEqual(config['location'], 'Workshop')
        roster = self.get('/roster.json').json()
        self.assertIn(self.alice.id, [e['id'] for e in roster['employees']])
        self.assertTrue(self.kiosk.last_contact)

    def test_badge_sign_in_and_out(self):
        identify = self.post('/identify', {'method': 'badge', 'badge': 'ALICE01'}).json()
        self.assertEqual(identify['status'], 'ok')
        self.assertNotIn('pin', identify['employee'])
        result = self.post('/action', {
            'ticket': identify['ticket'], 'employee_id': self.alice.id, 'action': 'sign_in', 'answers': [],
        }).json()
        self.assertEqual(result['status'], 'signed_in')
        result = self.post('/action', {
            'ticket': identify['ticket'], 'employee_id': self.alice.id, 'action': 'sign_out',
        }).json()
        self.assertEqual(result['status'], 'signed_out')

    def test_pin(self):
        bad = self.post('/identify', {'method': 'name', 'employee_id': self.alice.id, 'pin': '0000'})
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(bad.json()['code'], 'bad_pin')
        good = self.post('/identify', {'method': 'name', 'employee_id': self.alice.id, 'pin': '1234'}).json()
        self.assertEqual(good['status'], 'ok')

    def test_ticket_required(self):
        result = self.post('/action', {'ticket': 'forged', 'employee_id': self.alice.id, 'action': 'sign_in'})
        self.assertEqual(result.status_code, 401)
        self.assertFalse(self.env['hr.attendance'].search_count([('employee_id', '=', self.alice.id)]))
        identify = self.post('/identify', {'method': 'badge', 'badge': 'BOB01'}).json()
        result = self.post('/action', {'ticket': identify['ticket'], 'employee_id': self.alice.id, 'action': 'sign_in'})
        self.assertEqual(result.status_code, 401, "Bob's ticket cannot sign Alice in")

    def test_sync(self):
        start = fields.Datetime.now() - timedelta(hours=3)
        events = [
            {'id': 'a', 'employee_id': self.alice.id, 'action': 'sign_in',
             'time': start.strftime('%Y-%m-%dT%H:%M:%SZ'), 'answers': []},
            {'id': 'b', 'employee_id': self.alice.id, 'action': 'sign_out',
             'time': (start + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')},
        ]
        result = self.post('/sync', {'events': events}).json()
        self.assertEqual([r['status'] for r in result['results']], ['signed_in', 'signed_out'])
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)])
        self.assertEqual(attendance.check_in, start)
        self.assertEqual(attendance.check_out, start + timedelta(hours=2))
        self.assertTrue(attendance.kiosk_offline_in)
        # Re-sending the same events changes nothing.
        self.post('/sync', {'events': events})
        self.assertEqual(self.env['hr.attendance'].search_count([('employee_id', '=', self.alice.id)]), 1)

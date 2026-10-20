# -*- coding: utf-8 -*-
import json

from odoo.tests import HttpCase, tagged

from odoo.addons.iot_interfaces.tests.common import pair

from .common import EmbroideryCase


class TestStatusBoard(EmbroideryCase):

    def test_display_data(self):
        board = self.env['embroidery.status.board'].create({
            'name': 'Workshop Wall', 'machine_ids': [(6, 0, self.machine.ids)], 'tz': 'Europe/London',
        })
        other_job = self.env['embroidery.job'].create({
            'title': 'Caps', 'design_id': self.design.id, 'machine_id': self.machine.id, 'state': 'ready',
        })
        self.job.action_confirm()
        data = board._display_data(image_url=lambda design: 'design/%s' % design.id)
        machine = data['machines'][0]
        self.assertEqual(machine['status'], 'offline')
        self.assertIsNone(machine['job'])
        self.assertEqual([q['name'] for q in machine['queue']], [other_job.name, self.job.name])

        self.job.action_send_to_machine()
        self.job.stitchout_ids._apply_report({'status': 'stitching', 'stitch': 75})
        data = board._display_data(image_url=lambda design: 'design/%s' % design.id)
        machine = data['machines'][0]
        self.assertEqual(machine['job']['name'], self.job.name)
        self.assertEqual(machine['job']['preview_url'], 'design/%s' % self.design.id)
        self.assertEqual(machine['stitchout']['progress'], 50.0)
        self.assertEqual(machine['stitchout']['color_name'], 'Black')
        self.assertEqual([q['name'] for q in machine['queue']], [other_job.name])
        self.assertEqual(data['board']['layout'], 'grid')
        self.assertTrue(data['board']['show']['customer'])

        board.show_queue = False
        self.assertEqual(board._display_data(image_url=str)['machines'][0]['queue'], [])
        board.show_offline = False
        self.assertEqual(board._display_data(image_url=str)['machines'], [])


@tagged('post_install', '-at_install')
class TestDisplayApi(HttpCase):

    def test_display(self):
        machine = self.env['embroidery.machine'].create({'name': 'PR1060W #1'})
        board = self.env['embroidery.status.board'].create({
            'name': 'Workshop Wall', 'layout': 'focus', 'machine_ids': [(6, 0, machine.ids)],
        })
        display = self.env['iot.node'].create({'name': 'Workshop TV', 'role': 'embroidery_display',
                                               'embroidery_board_id': board.id})

        self.assertEqual(self.url_open('/embroidery/node/v1/display/data.json').status_code, 401)
        signer = pair(display, mac='dc:a6:32:00:00:05')

        def get(path):
            self.env.invalidate_all()
            response = self.url_open(path, headers=signer.headers('GET', path))
            self.env.invalidate_all()
            return response

        page = get('/embroidery/node/v1/display/page')
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-url="data.json"', page.text)
        data = get('/embroidery/node/v1/display/data.json?w=1920&h=1080').json()
        self.assertEqual(data['board']['layout'], 'focus')
        self.assertEqual([m['name'] for m in data['machines']], ['PR1060W #1'])
        self.assertEqual(data['display'], 'Workshop TV')
        self.assertEqual(display.screen_size, '1920x1080')
        self.assertTrue(display.is_online)

        display.action_reload_screen()
        self.assertEqual(get('/embroidery/node/v1/display/data.json').json()['reload'], 1)
        # The check-in tells the Node agent the page its local address opens.
        hello = '/iot/v1/hello'
        body = json.dumps({'version': '1.0.0'}).encode()
        self.env.invalidate_all()
        response = self.url_open(hello, data=body, headers={**signer.headers('POST', hello, body),
                                                             'Content-Type': 'application/json'})
        self.assertEqual(response.json()['program']['home'], '/embroidery/node/v1/display/page')

        # Logged-in users can preview the board.
        self.authenticate('admin', 'admin')
        preview = self.url_open('/embroidery/board/%s/preview/data.json' % board.id)
        self.assertEqual(preview.json()['board']['title'], 'Workshop Wall')

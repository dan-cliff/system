from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.iot_interfaces.tests.common import pair


class TestDisplayScreenSetup(TransactionCase):

    def setUp(self):
        super().setUp()
        self.counter = self.env['live.counter'].create({'name': 'Shop Window', 'include_pos_orders': False})

    def test_counter_instead_of_board(self):
        screen = self.env['iot.node'].create({
            'name': 'Shop TV', 'role': 'embroidery_display',
            'display_content': 'live_counter', 'live_counter_id': self.counter.id,
        })
        self.assertTrue(screen._shows_live_counter())
        self.assertEqual(self.counter.display_count, 1)
        with self.assertRaises(ValidationError):
            screen.live_counter_id = False
        with self.assertRaises(ValidationError):
            screen.display_content = 'embroidery_board'  # and no board chosen

    def test_switching_reloads_the_screen(self):
        board = self.env['embroidery.status.board'].create({'name': 'Workshop Wall'})
        screen = self.env['iot.node'].create({
            'name': 'Shop TV', 'role': 'embroidery_display', 'embroidery_board_id': board.id,
        })
        self.assertEqual(screen.display_content, 'embroidery_board')
        screen.write({'display_content': 'live_counter', 'live_counter_id': self.counter.id})
        self.assertEqual(screen.reload_counter, 1)


@tagged('post_install', '-at_install')
class TestDisplayScreenApi(HttpCase):

    def test_screen_shows_private_counter(self):
        counter = self.env['live.counter'].create({'name': 'Shop Window', 'include_pos_orders': False})
        self.assertEqual(counter.visibility, 'private')
        board = self.env['embroidery.status.board'].create({'name': 'Workshop Wall'})
        screen = self.env['iot.node'].create({
            'name': 'Shop TV', 'role': 'embroidery_display', 'embroidery_board_id': board.id,
        })
        signer = pair(screen, mac='dc:a6:32:00:00:07')

        def get(path):
            self.env.invalidate_all()
            response = self.url_open(path, headers=signer.headers('GET', path))
            self.env.invalidate_all()
            return response

        # Showing the board, the live data asks the page to switch back.
        self.assertTrue(get('/embroidery/node/v1/display/live_data.json').json()['switch_page'])

        screen.write({'display_content': 'live_counter', 'live_counter_id': counter.id})
        # The status board page still open is told to reload into the live page.
        self.assertTrue(get('/embroidery/node/v1/display/data.json').json()['switch_page'])
        page = get('/embroidery/node/v1/display/page')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Shop Window', page.text)
        self.assertIn('live_data.json', page.text)
        data = get('/embroidery/node/v1/display/live_data.json?places=1').json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['reload'], screen.reload_counter)
        self.assertIn('places', data)

        # Unsigned requests are refused.
        self.assertEqual(self.url_open('/embroidery/node/v1/display/live_data.json').status_code, 401)

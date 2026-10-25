import json
from datetime import date, datetime
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import TransactionCase


class LiveCounterCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.gb = cls.env.ref('base.uk')
        cls.fr = cls.env.ref('base.fr')
        cls.product = cls.env['product.product'].create({
            'name': 'Lavender Soap', 'list_price': 10.0, 'taxes_id': [(6, 0, [])],
        })
        cls.buyer = cls.env['res.partner'].create({
            'name': 'Jane Buyer', 'street': '1 Secret Lane', 'city': 'Cardiff',
            'country_id': cls.gb.id,
        })
        cls.team_web = cls.env['crm.team'].create({'name': 'Web Team'})
        cls.team_shop = cls.env['crm.team'].create({'name': 'Shop Team'})
        cls.counter = cls.env['live.counter'].create({
            'name': 'Today', 'tz': 'Europe/London', 'include_pos_orders': False,
        })

    @classmethod
    def _sell(cls, qty=2, team=None, partner=None):
        order = cls.env['sale.order'].create({
            'partner_id': (partner or cls.buyer).id,
            'team_id': (team or cls.team_web).id,
            'order_line': [(0, 0, {'product_id': cls.product.id, 'product_uom_qty': qty, 'price_unit': 10.0})],
        })
        order.action_confirm()
        return order


class TestLiveCounter(LiveCounterCommon):

    def test_period_start_uses_timezone(self):
        now = datetime(2026, 7, 15, 10, 0)  # Wednesday, British Summer Time
        self.counter.period = 'today'
        self.assertEqual(self.counter._period_start(now), datetime(2026, 7, 14, 23, 0))
        self.counter.period = 'week'
        self.assertEqual(self.counter._period_start(now), datetime(2026, 7, 12, 23, 0))
        self.counter.period = 'month'
        self.assertEqual(self.counter._period_start(now), datetime(2026, 6, 30, 23, 0))
        self.counter.period = 'year'
        self.assertEqual(self.counter._period_start(now), datetime(2026, 1, 1, 0, 0))
        self.counter.write({'period': 'since', 'date_from': date(2026, 3, 1)})
        self.assertEqual(self.counter._period_start(now), datetime(2026, 3, 1, 0, 0))
        self.assertEqual(self.counter._period_label(), 'Since 01/03/2026')

    def test_totals_and_recent_sales(self):
        first = self._sell(qty=2)
        second = self._sell(qty=3, team=self.team_shop)
        self.env['sale.order'].create({  # a quotation is not a sale
            'partner_id': self.buyer.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 9, 'price_unit': 10.0})],
        })
        data = self.counter._live_data(with_places=True)
        self.assertEqual(data['count'], 2)
        self.assertAlmostEqual(data['total'], first.amount_total + second.amount_total)
        self.assertEqual({c['name'] for c in data['channels']}, {'Web Team', 'Shop Team'})
        keys = [sale['key'] for sale in data['recent']]
        self.assertEqual(set(keys), {f'so-{first.id}', f'so-{second.id}'})
        sale = data['recent'][0]
        self.assertEqual(sale['city'], 'Cardiff')
        self.assertEqual(sale['country_code'], 'GB')
        self.assertFalse(sale['in_store'])
        self.assertTrue(data['places'])

    def test_customer_details_never_sent(self):
        self._sell()
        payload = json.dumps(self.counter._live_data(with_places=True))
        self.assertNotIn('Jane Buyer', payload)
        self.assertNotIn('Secret Lane', payload)
        self.counter.show_city = False
        self.assertEqual(self.counter._live_data()['recent'][0]['city'], '')

    def test_team_filter(self):
        self._sell(qty=1, team=self.team_web)
        self._sell(qty=1, team=self.team_shop)
        self.counter.team_ids = self.team_shop
        data = self.counter._live_data()
        self.assertEqual(data['count'], 1)
        self.assertEqual([c['name'] for c in data['channels']], ['Shop Team'])

    def test_untaxed_amounts(self):
        tax_group = self.env['account.tax.group'].create({'name': 'VAT', 'country_id': self.gb.id})
        tax = self.env['account.tax'].create({
            'name': 'VAT 20', 'amount': 20.0, 'type_tax_use': 'sale', 'tax_group_id': tax_group.id,
            'country_id': self.gb.id,
        })
        order = self._sell(qty=1)
        order.order_line.tax_ids = tax
        self.counter.tax_included = False
        self.assertAlmostEqual(self.counter._live_data()['total'], order.amount_untaxed)
        self.counter.tax_included = True
        self.assertAlmostEqual(self.counter._live_data()['total'], order.amount_total)

    def test_towns_are_queued_then_used(self):
        Location = self.env['live.counter.location']
        self._sell()
        self.counter._live_data()
        location = Location.search([('city_key', '=', 'cardiff'), ('country_id', '=', self.gb.id)])
        self.assertEqual(location.state, 'pending')
        self.assertIsNone(self.counter._live_data()['recent'][0]['lat'])

        with patch.object(type(self.env['base.geocoder']), 'geo_find', return_value=(51.4816, -3.1791)):
            Location._cron_geocode()
        self.assertEqual(location.state, 'done')
        sale = self.counter._live_data()['recent'][0]
        self.assertEqual((sale['lat'], sale['lng']), (51.5, -3.2))

    def test_town_not_found_gives_up(self):
        location = self.env['live.counter.location'].create({'city': 'Nowhere', 'country_id': self.fr.id})
        with patch.object(type(self.env['base.geocoder']), 'geo_find', return_value=None):
            for _attempt in range(3):
                location._geocode()
        self.assertEqual(location.state, 'failed')

    def test_private_access(self):
        viewer = new_test_user(self.env, 'lsc_viewer', groups='base.group_user,live_sales_counter.group_live_counter_view_all')
        base_only = new_test_user(self.env, 'lsc_base', groups='base.group_user,live_sales_counter.group_live_counter_user')
        outsider = new_test_user(self.env, 'lsc_outsider', groups='base.group_user')
        public = self.env.ref('base.public_user')
        self.assertTrue(self.counter._can_view(viewer))
        self.assertFalse(self.counter._can_view(base_only))
        self.assertFalse(self.counter._can_view(outsider))
        self.assertFalse(self.counter._can_view(public))
        self.counter.visibility = 'public'
        self.assertTrue(self.counter._can_view(public))

    def test_permissions(self):
        Counter = self.env['live.counter']
        owner = new_test_user(self.env, 'lsc_owner', groups='base.group_user,live_sales_counter.group_live_counter_edit_own')
        other = new_test_user(self.env, 'lsc_other', groups='base.group_user,live_sales_counter.group_live_counter_edit_own')
        mine = Counter.with_user(owner).create({'name': 'Mine', 'include_pos_orders': False})
        mine.name = 'Still mine'
        self.assertTrue(mine._can_view(owner))
        self.assertFalse(mine._can_view(other))
        self.assertFalse(Counter.with_user(other).search([('id', '=', mine.id)]))
        with self.assertRaises(AccessError):
            mine.unlink()
        # Without any permission the technical group sees nothing.
        nobody = new_test_user(self.env, 'lsc_nobody', groups='base.group_user,live_sales_counter.group_live_counter_user')
        self.assertFalse(Counter.with_user(nobody).search([]))

    def test_open_buttons_stay_on_this_site(self):
        self.assertEqual(self.counter.action_open_page()['url'], f'/live-sales/{self.counter.access_token}')
        self.assertEqual(self.counter.action_open_demo()['url'], f'/live-sales/{self.counter.access_token}?demo=1')

    def test_new_link(self):
        token = self.counter.access_token
        self.counter.action_regenerate_token()
        self.assertNotEqual(self.counter.access_token, token)
        self.assertTrue(self.counter.page_url.endswith(f'/live-sales/{self.counter.access_token}'))


@tagged('post_install', '-at_install')
class TestLiveCounterHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.counter = self.env['live.counter'].create({'name': 'Shop Window', 'include_pos_orders': False})

    def test_public_page(self):
        self.counter.visibility = 'public'
        page = self.url_open(f'/live-sales/{self.counter.access_token}')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Shop Window', page.text)
        data = self.url_open(f'/live-sales/{self.counter.access_token}/data?places=1')
        self.assertEqual(data.status_code, 200)
        self.assertIn('total', data.json())

    def test_private_page_needs_sign_in(self):
        page = self.url_open(f'/live-sales/{self.counter.access_token}', allow_redirects=False)
        self.assertIn(page.status_code, (302, 303))
        self.assertIn('/web/login', page.headers['Location'])
        self.assertEqual(self.url_open(f'/live-sales/{self.counter.access_token}/data').status_code, 403)
        self.authenticate('admin', 'admin')
        self.assertEqual(self.url_open(f'/live-sales/{self.counter.access_token}/data').status_code, 200)

    def test_unknown_link(self):
        self.assertEqual(self.url_open('/live-sales/not-a-token').status_code, 404)

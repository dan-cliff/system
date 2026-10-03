import json

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestWebsiteDashboard(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login='cdw_manager',
            groups='base.group_user,custom_dashboard.group_dashboard_manager,website.group_website_designer',
        )
        # A data user who can read contacts but not users
        cls.data_user = new_test_user(cls.env, login='cdw_data', groups='base.group_user')
        cls.env['res.partner'].create([{'name': 'CDW Alpha', 'color': 4}, {'name': 'CDW Beta', 'color': 6}])
        Fields = cls.env['ir.model.fields']
        cls.dashboard = cls.env['custom.dashboard'].create({
            'name': 'Public Stats',
            'website_data_user_id': cls.data_user.id,
        })
        Widget = cls.env['custom.dashboard.widget']
        cls.kpi = Widget.create({
            'dashboard_id': cls.dashboard.id,
            'type_id': cls.env.ref('custom_dashboard.widget_type_kpi').id,
            'name': 'Colour total',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'domain': "[('name', 'like', 'CDW ')]",
            'measure_field_id': Fields._get('res.partner', 'color').id,
        })
        cls.secret = Widget.create({
            'dashboard_id': cls.dashboard.id,
            'type_id': cls.env.ref('custom_dashboard.widget_type_kpi').id,
            'name': 'System parameters',
            'model_id': cls.env['ir.model']._get('ir.config_parameter').id,
        })

    def _data(self):
        response = self.url_open(
            '/dashboards/data',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                             'params': {'dashboard_id': self.dashboard.id}}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_unpublished_is_hidden(self):
        self.assertEqual(self.url_open(self.dashboard.website_url).status_code, 404)
        self.assertIn('error', self._data())

    def test_manager_can_preview_unpublished(self):
        self.authenticate('cdw_manager', 'cdw_manager')
        response = self.url_open(self.dashboard.website_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('not published', response.text)

    def test_published_page_and_data(self):
        self.dashboard.is_published = True
        self.assertTrue(self.dashboard.website_url.startswith('/dashboards/public-stats-'))
        page = self.url_open(self.dashboard.website_url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('custom_dashboard_website.PublicDashboard', page.text)
        index = self.url_open('/dashboards')
        self.assertIn(self.dashboard.website_url, index.text)

        result = self._data()['result']
        self.assertEqual(result['data'][str(self.kpi.id)], {'value': 10.0})
        # Read as the data user, who has no access to system parameters
        self.assertIn('error', result['data'][str(self.secret.id)])

    def test_publish_needs_data_user(self):
        self.dashboard.website_data_user_id = False
        with self.assertRaises(ValidationError):
            self.dashboard.is_published = True

    def test_website_menu_follows_publishing(self):
        self.dashboard.write({'website_show_in_menu': True})
        self.assertFalse(self.dashboard.website_menu_id)
        self.dashboard.is_published = True
        menu = self.dashboard.website_menu_id
        self.assertTrue(menu)
        self.assertEqual(menu.url, self.dashboard.website_url)
        self.dashboard.name = 'Renamed Stats'
        self.assertEqual(menu.name, 'Renamed Stats')
        self.dashboard.is_published = False
        self.assertFalse(menu.exists())

    def test_viewer_cannot_publish(self):
        viewer = new_test_user(self.env, login='cdw_viewer', groups='base.group_user,custom_dashboard.group_dashboard_user')
        self.dashboard.user_ids = [(4, viewer.id)]
        self.assertFalse(self.dashboard.with_user(viewer).can_publish)

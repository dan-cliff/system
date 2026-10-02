from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCustomDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login='cd_manager', groups='base.group_user,custom_dashboard.group_dashboard_manager',
        )
        cls.viewer = new_test_user(
            cls.env, login='cd_viewer', groups='base.group_user,custom_dashboard.group_dashboard_user',
        )
        cls.outsider = new_test_user(
            cls.env, login='cd_outsider', groups='base.group_user,custom_dashboard.group_dashboard_user',
        )
        cls.dashboard = cls.env['custom.dashboard'].create({
            'name': 'Partners',
            'user_ids': [(4, cls.viewer.id)],
        })
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.country_be = cls.env.ref('base.be')
        cls.country_fr = cls.env.ref('base.fr')
        Partner = cls.env['res.partner']
        Partner.create([
            {'name': 'CD Alpha', 'country_id': cls.country_be.id, 'color': 2, 'is_company': True},
            {'name': 'CD Beta', 'country_id': cls.country_be.id, 'color': 3},
            {'name': 'CD Gamma', 'country_id': cls.country_fr.id, 'color': 5, 'is_company': True},
        ])

    def _field(self, name):
        return self.env['ir.model.fields']._get('res.partner', name)

    def _widget(self, code, **vals):
        return self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_%s' % code).id,
            'name': code,
            'model_id': self.partner_model.id,
            'domain': "[('name', 'like', 'CD ')]",
            **vals,
        })

    def test_column_count_by_country(self):
        widget = self._widget('column', groupby_field_id=self._field('country_id').id)
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(dict(zip(data['labels'], data['values'])), {
            self.country_be.display_name: 2.0,
            self.country_fr.display_name: 1.0,
        })

    def test_bar_sum_sorted_with_limit(self):
        widget = self._widget(
            'bar',
            groupby_field_id=self._field('country_id').id,
            measure_field_id=self._field('color').id,
            aggregate='sum',
            sort='value_desc',
            limit=1,
        )
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(data['labels'], [self.country_be.display_name])
        self.assertEqual(data['values'], [5.0])

    def test_series_split(self):
        widget = self._widget(
            'stacked_column',
            groupby_field_id=self._field('country_id').id,
            series_field_id=self._field('is_company').id,
        )
        data = widget.get_widget_data()[widget.id]
        series = {s['label']: s['values'] for s in data['series']}
        be = data['labels'].index(self.country_be.display_name)
        self.assertEqual(series['Yes'][be], 1.0)
        self.assertEqual(series['No'][be], 1.0)

    def test_date_grouping_label_is_day_first(self):
        widget = self._widget(
            'line', groupby_field_id=self._field('create_date').id, groupby_interval='day',
        )
        data = widget.get_widget_data()[widget.id]
        self.assertRegex(data['labels'][0], r'^\d{2}/\d{2}/\d{4}$')

    def test_kpi_and_points(self):
        kpi = self._widget('kpi', measure_field_id=self._field('color').id, aggregate='max')
        self.assertEqual(kpi.get_widget_data()[kpi.id], {'value': 5.0})
        scatter = self._widget(
            'scatter', measure_field_id=self._field('color').id, measure2_field_id=self._field('color').id,
        )
        self.assertEqual(len(scatter.get_widget_data()[scatter.id]['points']), 3)

    def test_bad_domain_reports_error(self):
        widget = self._widget('column', groupby_field_id=self._field('country_id').id, domain='[(')
        self.assertIn('error', widget.get_widget_data()[widget.id])

    def test_layout_and_editing_rights(self):
        config = self.dashboard.with_user(self.manager).add_widget('column', x=2, y=1, w=6, h=3)
        widget = self.env['custom.dashboard.widget'].browse(config['id'])
        self.dashboard.with_user(self.manager).save_layout([{'id': widget.id, 'x': 4, 'y': 0, 'w': 20, 'h': 2}])
        self.assertEqual((widget.pos_x, widget.pos_y, widget.width, widget.height), (4, 0, 12, 2))
        with self.assertRaises(AccessError):
            self.dashboard.with_user(self.viewer).save_layout([{'id': widget.id, 'x': 0, 'y': 0, 'w': 1, 'h': 1}])

    def test_sharing(self):
        Dashboard = self.env['custom.dashboard']
        self.assertIn(self.dashboard, Dashboard.with_user(self.viewer).search([]))
        self.assertNotIn(self.dashboard, Dashboard.with_user(self.outsider).search([]))
        self.dashboard.group_ids = [(4, self.env.ref('base.group_user').id)]
        self.assertIn(self.dashboard, Dashboard.with_user(self.outsider).search([]))
        result = self.dashboard.with_user(self.viewer).get_dashboard()
        self.assertFalse(result['can_edit'])
        self.assertEqual(result['palette'], [])

    def test_copy_dashboard_copies_widgets(self):
        self._widget('pie', groupby_field_id=self._field('country_id').id)
        copy = self.dashboard.copy()
        self.assertEqual(len(copy.widget_ids), 1)

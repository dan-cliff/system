from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, freeze_time, new_test_user, tagged


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

    def test_elapsed_between_counts_whole_units(self):
        between = self.env['custom.dashboard.widget']._elapsed_between
        start = date(2026, 1, 31)
        self.assertEqual(between(start, date(2026, 3, 1), 'day'), 29.0)
        self.assertEqual(between(start, date(2026, 2, 13), 'week'), 1.0)
        self.assertEqual(between(start, date(2026, 2, 27), 'month'), 0.0)
        # Month-end anniversaries fall on the last day of shorter months
        self.assertEqual(between(start, date(2026, 2, 28), 'month'), 1.0)
        self.assertEqual(between(start, date(2026, 3, 31), 'month'), 2.0)
        self.assertEqual(between(date(2024, 2, 29), date(2026, 2, 27), 'year'), 1.0)
        self.assertEqual(between(date(2024, 2, 29), date(2026, 2, 28), 'year'), 2.0)
        # A date in the future counts down
        self.assertEqual(between(date(2026, 10, 10), date(2026, 10, 3), 'day'), -7.0)
        self.assertEqual(between(date(2026, 10, 10), date(2026, 10, 3), 'week'), -1.0)

    @freeze_time('2026-10-03')
    def test_kpi_time_since_latest_date(self):
        currency = self.env['res.currency'].create({'name': 'CDX', 'symbol': 'X'})
        self.env['res.currency.rate'].create([
            {'currency_id': currency.id, 'name': '2026-06-01', 'rate': 1.0},
            {'currency_id': currency.id, 'name': '2026-09-19', 'rate': 1.1},
        ])
        widget = self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_kpi').id,
            'name': 'Since last rate',
            'model_id': self.env['ir.model']._get('res.currency.rate').id,
            'domain': "[('currency_id.name', '=', 'CDX')]",
            'value_mode': 'elapsed',
            'elapsed_field_id': self.env['ir.model.fields']._get('res.currency.rate', 'name').id,
            'elapsed_unit': 'day',
        })
        self.assertEqual(widget.get_widget_data()[widget.id], {'value': 14.0, 'latest': '19/09/2026'})
        widget.elapsed_unit = 'week'
        self.assertEqual(widget.get_widget_data()[widget.id]['value'], 2.0)

        widget.domain = "[('currency_id.name', '=', 'NONE')]"
        self.assertEqual(widget.get_widget_data()[widget.id], {'value': None, 'latest': False})

        widget.elapsed_field_id = False
        self.assertIn('error', widget.get_widget_data()[widget.id])

    @freeze_time('2026-10-03 10:00:00')
    def test_kpi_time_since_latest_datetime(self):
        widget = self._widget(
            'kpi', value_mode='elapsed', elapsed_unit='day',
            elapsed_field_id=self._field('create_date').id,
        )
        # Partners created in this test run are stamped "now"
        self.assertEqual(widget.get_widget_data()[widget.id]['value'], 0.0)

    def test_frame_options_in_config(self):
        widget = self._widget('column', groupby_field_id=self._field('country_id').id)
        config = widget._get_config()
        self.assertTrue(config['show_border'])
        self.assertFalse(config['show_shadow'])
        widget.write({'show_border': False, 'show_shadow': True})
        config = widget._get_config()
        self.assertFalse(config['show_border'])
        self.assertTrue(config['show_shadow'])

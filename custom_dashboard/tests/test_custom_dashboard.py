from datetime import date

from odoo.exceptions import AccessError, ValidationError
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

    # ------------------------------------------------------------------
    # Map widget
    # ------------------------------------------------------------------
    def _map_widget(self, **vals):
        return self._widget('map', **vals)

    def test_map_countries_from_contacts(self):
        widget = self._map_widget(map_level='country')
        data = widget.get_widget_data()[widget.id]
        regions = {r['key']: r for r in data['regions']}
        self.assertEqual(regions['BE']['value'], 2.0)
        self.assertEqual(regions['FR']['value'], 1.0)
        self.assertEqual(regions['BE']['country'], 'BE')

    def test_map_sum_and_country_focus(self):
        widget = self._map_widget(
            map_level='country', map_country_id=self.country_be.id,
            measure_field_id=self._field('color').id, aggregate='sum',
        )
        data = widget.get_widget_data()[widget.id]
        self.assertEqual([(r['key'], r['value']) for r in data['regions']], [('BE', 5.0)])
        config = widget._get_config()
        self.assertEqual(config['map_country_code'], 'BE')
        self.assertEqual(config['map_level'], 'country')

    def test_map_states_through_another_model(self):
        victoria = self.env['res.country.state'].search(
            [('country_id.code', '=', 'AU'), ('code', '=', 'VIC')], limit=1)
        partner = self.env['res.partner'].create({
            'name': 'CD Vic', 'country_id': victoria.country_id.id, 'state_id': victoria.id,
        })
        user = new_test_user(self.env, login='cd_map_user', partner_id=partner.id)
        widget = self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_map').id,
            'name': 'Users by state',
            'model_id': self.env['ir.model']._get('res.users').id,
            'domain': "[('id', '=', %d)]" % user.id,
            'map_address_path': 'partner_id',
            'map_level': 'state',
            'map_state_id': victoria.id,
        })
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(data['regions'], [{
            'key': 'AU-VIC', 'name': victoria.name, 'country': 'AU', 'value': 1.0, 'count': 1,
        }])
        self.assertEqual(widget._get_config()['map_state_key'], 'AU-VIC')
        self.assertEqual(widget._get_config()['map_country_code'], 'AU')

        # Multi-step paths work too
        widget.write({'map_address_path': 'company_id.partner_id', 'map_level': 'country', 'map_state_id': False})
        self.assertNotIn('error', widget.get_widget_data()[widget.id])

    def test_map_rejects_bad_address_paths(self):
        widget = self._map_widget()
        for path in ('name', 'country_id', 'nope'):
            widget.map_address_path = path
            self.assertIn('error', widget.get_widget_data()[widget.id], path)
        users_widget = self._map_widget(model_id=self.env['ir.model']._get('res.users').id, domain='[]')
        self.assertIn('error', users_widget.get_widget_data()[users_widget.id])

    def test_map_contact_locations(self):
        widget = self._map_widget(map_level='point')
        data = widget.get_widget_data()[widget.id]
        if 'partner_latitude' not in self.env['res.partner']._fields:
            self.assertIn('base_geolocalize', data['error'])
            return
        self.env['res.partner'].search([('name', 'like', 'CD ')]).write({
            'partner_latitude': -36.7571, 'partner_longitude': 144.2794, 'city': 'Bendigo',
        })
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(data['points'], [{
            'lat': -36.76, 'lng': 144.28, 'value': 3.0, 'count': 3, 'name': 'Bendigo',
        }])

    # ------------------------------------------------------------------
    # Colours
    # ------------------------------------------------------------------
    def _clear_default_colours(self):
        params = self.env['ir.config_parameter'].sudo()
        for i in range(1, 7):
            params.set_param('custom_dashboard.default_color_%d' % i, False)

    def test_widget_colours_fall_back_to_defaults(self):
        self._clear_default_colours()
        widget = self._widget('pie', groupby_field_id=self._field('country_id').id)
        self.assertEqual(widget._get_config()['colors'], [])

        settings = self.env['res.config.settings'].create({
            'cd_default_color_1': '#112233', 'cd_default_color_3': '#445566',
        })
        settings.execute()
        widget.invalidate_recordset()
        self.assertEqual(widget._get_config()['colors'], ['#112233', '#445566'])
        self.assertEqual(widget._get_config()['color'], '#112233')
        self.assertIn('#445566', widget.colors_preview)

        widget.write({'custom_colors': True, 'color': '#aa0000', 'color_2': '#00aa00'})
        self.assertEqual(widget._get_config()['colors'], ['#aa0000', '#00aa00'])
        # Custom colours switched on but all empty still use the defaults
        widget.write({'color': False, 'color_2': False})
        self.assertEqual(widget._get_config()['colors'], ['#112233', '#445566'])

    def test_widget_colours_must_be_colours(self):
        widget = self._widget('pie', groupby_field_id=self._field('country_id').id)
        with self.assertRaises(ValidationError):
            widget.color_4 = 'blue-ish'

    def test_custom_colours_start_from_defaults(self):
        self._clear_default_colours()
        self.env['ir.config_parameter'].sudo().set_param('custom_dashboard.default_color_1', '#123456')
        widget = self._widget('pie', groupby_field_id=self._field('country_id').id)
        widget.custom_colors = True
        widget._onchange_custom_colors()
        self.assertEqual(widget.color, '#123456')
        self.assertFalse(widget.color_2)

    # ------------------------------------------------------------------
    # Pivot table axes
    # ------------------------------------------------------------------
    def test_pivot_show_all_selection_rows_in_sequence(self):
        widget = self._widget(
            'pivot', groupby_field_id=self._field('type').id, series_field_id=self._field('is_company').id,
            pivot_show_all_rows=True, pivot_show_all_columns=True,
            pivot_row_label='Address type', pivot_col_label='Company?',
        )
        data = widget.get_widget_data()[widget.id]
        selection = dict(self.env['res.partner']._fields['type']._description_selection(self.env))
        # Every option, in the selection's own order, even without records
        self.assertEqual(data['labels'], list(selection.values()))
        self.assertEqual([s['label'] for s in data['series']], ['Yes', 'No'])
        contact = data['labels'].index(selection['contact'])
        self.assertEqual(data['series'][0]['values'][contact], 2.0)
        self.assertEqual(data['series'][1]['values'][contact], 1.0)
        self.assertEqual(sum(data['series'][0]['values']), 2.0)
        config = widget._get_config()
        self.assertEqual((config['pivot_row_label'], config['pivot_col_label']), ('Address type', 'Company?'))

    def test_pivot_without_show_all_lists_only_used_values(self):
        widget = self._widget('pivot', groupby_field_id=self._field('type').id,
                              series_field_id=self._field('is_company').id)
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(len(data['labels']), 1)

    def test_pivot_axis_sorting(self):
        widget = self._widget(
            'pivot', groupby_field_id=self._field('country_id').id, series_field_id=self._field('is_company').id,
            pivot_row_sort='value_asc', pivot_col_sort='label',
        )
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(data['labels'], [self.country_fr.display_name, self.country_be.display_name])
        self.assertEqual([s['label'] for s in data['series']], ['No', 'Yes'])
        widget.pivot_row_sort = 'sequence'
        data = widget.get_widget_data()[widget.id]
        # Countries' own order is by name
        self.assertEqual(data['labels'], sorted(data['labels']))

    def test_pivot_show_all_fills_date_gaps(self):
        currency = self.env['res.currency'].create({'name': 'CDP', 'symbol': 'P'})
        self.env['res.currency.rate'].create([
            {'currency_id': currency.id, 'name': '2026-01-15', 'rate': 1.0},
            {'currency_id': currency.id, 'name': '2026-04-02', 'rate': 1.0},
        ])
        widget = self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_pivot').id,
            'name': 'Rates by month',
            'model_id': self.env['ir.model']._get('res.currency.rate').id,
            'domain': "[('currency_id', '=', %d)]" % currency.id,
            'groupby_field_id': self.env['ir.model.fields']._get('res.currency.rate', 'name').id,
            'groupby_interval': 'month',
            'series_field_id': self.env['ir.model.fields']._get('res.currency.rate', 'currency_id').id,
            'pivot_show_all_rows': True,
        })
        data = widget.get_widget_data()[widget.id]
        self.assertEqual(data['labels'], ['01/2026', '02/2026', '03/2026', '04/2026'])
        self.assertEqual(data['series'][0]['values'], [1.0, 0.0, 0.0, 1.0])

    def test_map_address_path_through_computed_field(self):
        # res.partner.self is computed (not stored), like an employee's User
        # Partner: the database can't group by it, so it's grouped in Python.
        widget = self._map_widget(
            map_level='country', map_address_path='self',
            measure_field_id=self._field('color').id, aggregate='sum',
        )
        data = widget.get_widget_data()[widget.id]
        self.assertNotIn('error', data)
        regions = {r['key']: (r['value'], r['count']) for r in data['regions']}
        self.assertEqual(regions, {'BE': (5.0, 2), 'FR': (5.0, 1)})

        widget.write({'aggregate': 'avg', 'map_country_id': self.country_be.id})
        data = widget.get_widget_data()[widget.id]
        self.assertEqual([(r['key'], r['value']) for r in data['regions']], [('BE', 2.5)])

    def test_pivot_hide_none_and_totals(self):
        self.env['res.partner'].create({'name': 'CD Nowhere', 'is_company': True})
        widget = self._widget(
            'pivot', groupby_field_id=self._field('country_id').id, series_field_id=self._field('parent_id').id,
        )
        data = widget.get_widget_data()[widget.id]
        self.assertIn('None', data['labels'])
        self.assertIn('None', [s['label'] for s in data['series']])
        config = widget._get_config()
        self.assertTrue(config['pivot_row_totals'] and config['pivot_column_totals'])

        widget.write({
            'pivot_hide_none_rows': True, 'pivot_hide_none_columns': True,
            'pivot_hide_row_totals': True, 'pivot_hide_column_totals': True,
        })
        data = widget.get_widget_data()[widget.id]
        self.assertNotIn('None', data['labels'])
        self.assertEqual(sorted(data['labels']), sorted([self.country_be.display_name, self.country_fr.display_name]))
        self.assertNotIn('None', [s['label'] for s in data['series']])
        config = widget._get_config()
        self.assertFalse(config['pivot_row_totals'] or config['pivot_column_totals'])

    def test_pivot_boolean_no_is_not_none(self):
        widget = self._widget(
            'pivot', groupby_field_id=self._field('is_company').id, series_field_id=self._field('country_id').id,
            pivot_hide_none_rows=True,
        )
        self.assertEqual(sorted(widget.get_widget_data()[widget.id]['labels']), ['No', 'Yes'])

    def test_pivot_sequence_reversed(self):
        self.env['res.partner'].create({'name': 'CD Nowhere'})
        widget = self._widget(
            'pivot', groupby_field_id=self._field('country_id').id, series_field_id=self._field('is_company').id,
            pivot_row_sort='sequence_desc', pivot_col_sort='sequence_desc',
        )
        data = widget.get_widget_data()[widget.id]
        names = sorted([self.country_be.display_name, self.country_fr.display_name])
        # Reversed sequence, with the "None" group still last
        self.assertEqual(data['labels'], names[::-1] + ['None'])
        self.assertEqual([s['label'] for s in data['series']], ['No', 'Yes'])

    # ------------------------------------------------------------------
    # User relationship filter
    # ------------------------------------------------------------------
    def _hierarchy(self):
        """boss > me > report > junior, each with a user and an employee."""
        if 'hr.employee' not in self.env:
            self.skipTest('Needs the Employees app')
        Employee = self.env['hr.employee']
        people = {}
        parent = Employee
        for name in ('boss', 'me', 'report', 'junior'):
            user = new_test_user(self.env, login='cd_h_%s' % name, groups='base.group_user')
            people[name] = (user, Employee.create({'name': name, 'user_id': user.id, 'parent_id': parent.id}))
            parent = people[name][1]
        # A peer of "me" who is not in my team
        peer = new_test_user(self.env, login='cd_h_peer', groups='base.group_user')
        people['peer'] = (peer, Employee.create({'name': 'peer', 'user_id': peer.id,
                                                 'parent_id': people['boss'][1].id}))
        return people

    def _user_kpi(self, people, scope, **vals):
        user_ids = [user.id for user, _employee in people.values()]
        return self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_table').id,
            'name': 'Users',
            'model_id': self.env['ir.model']._get('res.users').id,
            'domain': "[('id', 'in', %s)]" % user_ids,
            'groupby_field_id': self.env['ir.model.fields']._get('res.users', 'login').id,
            'user_filter_scope': scope,
            **vals,
        })

    def test_user_filter_scopes(self):
        people = self._hierarchy()
        me = people['me'][0]
        expected = {
            'self': ['cd_h_me'],
            'manager': ['cd_h_boss'],
            'team': ['cd_h_report'],
            'extended_team': ['cd_h_junior', 'cd_h_me', 'cd_h_report'],
        }
        for scope, logins in expected.items():
            widget = self._user_kpi(people, scope)
            data = widget._get_widget_data(self.env(user=me))[widget.id]
            self.assertEqual(sorted(data['labels']), logins, scope)
        # Without a scope everyone counts
        widget = self._user_kpi(people, False)
        self.assertEqual(len(widget._get_widget_data(self.env(user=me))[widget.id]['labels']), 5)

    def test_user_filter_through_a_field_and_on_employees(self):
        people = self._hierarchy()
        boss_user, boss_employee = people['boss']
        employee_ids = [employee.id for _user, employee in people.values()]
        widget = self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.dashboard.id,
            'type_id': self.env.ref('custom_dashboard.widget_type_table').id,
            'name': 'Team',
            'model_id': self.env['ir.model']._get('hr.employee').id,
            'domain': "[('id', 'in', %s)]" % employee_ids,
            'groupby_field_id': self.env['ir.model.fields']._get('hr.employee', 'name').id,
            'user_filter_scope': 'team',
        })
        boss_user.write({'group_ids': [(4, self.env.ref('hr.group_hr_user').id)]})
        data_env = self.env(user=boss_user)
        # The record itself is the employee
        self.assertEqual(sorted(widget._get_widget_data(data_env)[widget.id]['labels']), ['me', 'peer'])
        # Through a user field
        widget.user_filter_path = 'user_id'
        self.assertEqual(sorted(widget._get_widget_data(data_env)[widget.id]['labels']), ['me', 'peer'])

    def test_user_filter_needs_a_user_field(self):
        widget = self._widget('column', groupby_field_id=self._field('country_id').id, user_filter_scope='self')
        self.assertIn('error', widget.get_widget_data()[widget.id])
        widget.user_filter_path = 'country_id'
        self.assertIn('error', widget.get_widget_data()[widget.id])
        widget.user_filter_path = 'user_id'
        self.assertNotIn('error', widget.get_widget_data()[widget.id])

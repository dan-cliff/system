from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMultiScreen(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='multi_screen_user', groups='base.group_user')
        cls.Layout = cls.env['multi.screen.layout'].with_user(cls.user)

    def _layout(self, name, **vals):
        return self.Layout.create({
            'name': name,
            'window_ids': [
                (0, 0, {'name': 'List', 'screen_number': 1}),
                (0, 0, {'name': 'Record', 'screen_number': 2,
                        'placement_id': self.env.ref('multi_screen.placement_right_half').id}),
            ],
            **vals,
        })

    def test_single_launch_workspace(self):
        first = self._layout('First', launch_on_start=True)
        second = self._layout('Second', launch_on_start=True)
        self.assertFalse(first.launch_on_start)
        self.assertTrue(second.launch_on_start)
        self.assertEqual(self.Layout.get_workspaces()['launch_layout_id'], second.id)

    def test_workspace_data_uses_placement(self):
        layout = self._layout('Orders')
        self.assertEqual(layout.screen_count, 2)
        data = self.Layout.get_workspaces()
        windows = next(l for l in data['layouts'] if l['id'] == layout.id)['windows']
        self.assertEqual(windows[0]['url'], '/odoo')
        self.assertEqual((windows[1]['left_pct'], windows[1]['width_pct']), (50.0, 50.0))

    def test_save_from_windows(self):
        action = self.Layout.save_from_windows([
            {'name': 'Orders', 'url': '/odoo/sales', 'screen_number': 1,
             'left_pct': 0, 'top_pct': 0, 'width_pct': 100, 'height_pct': 100},
            {'name': 'Elsewhere', 'url': 'https://example.com', 'screen_number': 2,
             'left_pct': 60, 'top_pct': 0, 'width_pct': 70, 'height_pct': 100},
        ])
        layout = self.Layout.browse(action['res_id'])
        self.assertEqual(layout.user_id, self.user)
        self.assertEqual(layout.window_ids.mapped('url'), ['/odoo/sales', False])
        # Clamped so the window fits on its screen.
        self.assertEqual(layout.window_ids[1].width_pct, 40.0)

    def test_window_checks(self):
        layout = self._layout('Checks')
        with self.assertRaises(ValidationError):
            layout.window_ids[0].url = '//example.com'
        with self.assertRaises(ValidationError):
            layout.window_ids[0].write({'left_pct': 60, 'width_pct': 60})
        other = self._layout('Other')
        with self.assertRaises(ValidationError):
            layout.window_ids[0].open_records_on_id = other.window_ids[1]

    def test_users_keep_their_own_workspaces(self):
        mine = self._layout('Mine')
        someone = new_test_user(self.env, login='multi_screen_other', groups='base.group_user')
        self.assertNotIn(mine.id, [
            l['id'] for l in self.env['multi.screen.layout'].with_user(someone).get_workspaces()['layouts']
        ])

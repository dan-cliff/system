from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDashboardProfiles(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref('custom_dashboard.group_dashboard_user')
        cls.profile = cls.env['permission.profile'].create({'name': 'Section Leaders'})
        cls.user = new_test_user(cls.env, login='cd_profile_user', groups='base.group_user')
        cls.user.permission_profile_id = cls.profile
        Dashboard = cls.env['custom.dashboard']
        cls.shared = Dashboard.create({'name': 'Section Dashboard'})
        cls.other = Dashboard.create({'name': 'Finance Dashboard'})
        cls.widget = cls.env['custom.dashboard.widget'].create({
            'dashboard_id': cls.shared.id,
            'type_id': cls.env.ref('custom_dashboard.widget_type_text').id,
            'name': 'Welcome',
        })

    def test_profile_dashboards_grant_access(self):
        self.assertNotIn(self.group, self.user.all_group_ids)
        self.profile.dashboard_ids = self.shared
        self.assertIn(self.group, self.user.all_group_ids)
        self.assertEqual(self.shared.permission_profile_ids, self.profile)

        Dashboard = self.env['custom.dashboard'].with_user(self.user)
        self.assertEqual(Dashboard.search([('id', 'in', (self.shared | self.other).ids)]), self.shared)
        self.assertTrue(self.shared.with_user(self.user).get_dashboard()['widgets'])
        self.assertTrue(self.widget.with_user(self.user).get_widget_data())
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).get_dashboard()

    def test_access_removed_with_profile_dashboards(self):
        self.profile.dashboard_ids = self.shared
        self.profile.dashboard_ids = False
        self.assertNotIn(self.group, self.user.all_group_ids)
        # No Dashboards access left at all.
        with self.assertRaises(AccessError):
            self.env['custom.dashboard'].with_user(self.user).search([('id', '=', self.shared.id)])

    def test_sharing_from_the_dashboard_side(self):
        self.shared.permission_profile_ids = self.profile
        self.assertIn(self.group, self.user.all_group_ids)
        self.shared.permission_profile_ids = False
        self.assertNotIn(self.group, self.user.all_group_ids)

    def test_changing_profile_moves_access(self):
        self.profile.dashboard_ids = self.shared
        other_profile = self.env['permission.profile'].create({'name': 'Parents'})
        self.user.permission_profile_id = other_profile
        self.assertNotIn(self.group, self.user.all_group_ids)
        self.user.permission_profile_id = self.profile
        self.assertIn(self.group, self.user.all_group_ids)

    def test_manual_access_is_kept(self):
        manual = new_test_user(
            self.env, login='cd_profile_manual', groups='base.group_user,custom_dashboard.group_dashboard_user',
        )
        manual.permission_profile_id = self.profile
        self.profile.dashboard_ids = self.shared
        self.profile.dashboard_ids = False
        self.assertIn(self.group, manual.all_group_ids)

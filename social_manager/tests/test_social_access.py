from odoo.tests import tagged

from .common import SocialCommon


@tagged('post_install', '-at_install')
class TestSocialAccess(SocialCommon):

    def test_levels_created_per_platform_and_channel(self):
        for record in (self.platform, self.page_a):
            groups = record._social_access_groups()
            self.assertEqual(len(groups), 5)
            self.assertEqual(len(groups.privilege_id), 5, 'each level is its own privilege')
            self.assertTrue(all(self.env.ref('social_manager.group_social_user') in g.implied_ids for g in groups))
        self.assertIn(self.page_a.group_draft_id, self.page_a.group_publish_id.implied_ids)
        self.assertEqual(self.page_a.group_approve_id.privilege_id.name, 'Facebook - Page A / Approve Posts')
        self.assertEqual(self.platform.group_moderate_id.privilege_id.name, 'Facebook / Moderate Posts')

    def test_all_six_platforms_have_levels(self):
        platforms = self.env['social.platform'].search([])
        self.assertEqual(set(platforms.mapped('code')),
                         {'facebook', 'twitter', 'linkedin', 'instagram', 'tiktok', 'youtube'})
        self.assertTrue(all(len(p._social_access_groups()) == 5 for p in platforms))

    def test_rename_and_delete(self):
        self.page_a.name = 'Renamed'
        self.assertEqual(self.page_a.group_draft_id.privilege_id.name, 'Facebook - Renamed / Create and Edit Draft')
        groups = self.page_b._social_access_groups()
        privileges = groups.privilege_id
        self.page_b.unlink()
        self.assertFalse(groups.exists())
        self.assertFalse(privileges.exists())

    def test_platform_level_covers_channels(self):
        self.assertIn(self.platform.group_publish_id, self.page_a.access_group_ids)
        self.assertTrue(self.page_b.with_user(self.publisher)._user_has_level('publish'))
        self.assertTrue(self.page_a.with_user(self.drafter)._user_has_level('draft'))
        self.assertFalse(self.page_a.with_user(self.drafter)._user_has_level('publish'))
        self.assertFalse(self.page_b.with_user(self.drafter)._user_has_level('draft'))

    def test_record_rules(self):
        Channel = self.env['social.channel'].with_user(self.drafter)
        self.assertEqual(Channel.search([]), self.page_a)
        visible = self.env['social.channel'].with_user(self.publisher).search([])
        self.assertTrue(self.page_a | self.page_b <= visible)
        self.assertFalse(visible.filtered(lambda c: c.platform_id != self.platform))

    def test_permission_roles(self):
        if 'permission.role' not in self.env:
            self.skipTest('Permission Management is not installed')
        lines = self.env['permission.role.line'].search([('group_id', 'in', self.page_a._social_access_groups().ids)])
        self.assertEqual(len(lines.role_id), 5)
        self.assertIn('Social Manager: Facebook - Page A - Approve Posts', lines.role_id.mapped('name'))

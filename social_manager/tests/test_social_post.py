from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.social_manager.providers.facebook import FacebookProvider

from .common import SocialCommon


def fake_publish(self, post, channel):
    return {'external_id': '%s_%s' % (channel.external_id, post.id), 'url': 'https://example.com'}


@tagged('post_install', '-at_install')
class TestSocialPost(SocialCommon):

    def _post(self, user, channels, **vals):
        return self.env['social.post'].with_user(user).create(dict({
            'name': 'Hello', 'message': 'Hello world', 'channel_ids': [(6, 0, channels.ids)]}, **vals))

    def test_drafter_needs_approval(self):
        post = self._post(self.drafter, self.page_a)
        self.assertFalse(post.can_publish)
        with self.assertRaises(AccessError):
            post.action_publish_now()
        post.action_submit()
        self.assertEqual(post.state, 'pending')
        with self.assertRaises(AccessError):
            post.action_approve()
        with patch.object(FacebookProvider, 'publish', fake_publish):
            post.with_user(self.approver).action_approve()
        self.assertEqual(post.state, 'posted')
        self.assertEqual(post.approved_by_id, self.approver)
        self.assertEqual(post.publication_ids.external_id, 'pa_%s' % post.id)

    def test_state_only_changes_through_workflow(self):
        post = self._post(self.drafter, self.page_a)
        with self.assertRaises(AccessError):
            post.write({'state': 'scheduled'})
        with self.assertRaises(AccessError):
            self._post(self.drafter, self.page_a, state='posted')
        comment_post = self._post(self.publisher, self.page_a)
        with patch.object(FacebookProvider, 'publish', fake_publish):
            comment_post.action_publish_now()
        comment = self.env['social.comment'].create({
            'publication_id': comment_post.publication_ids.id, 'external_id': 'z', 'message': 'hi'})
        with self.assertRaises(AccessError):
            comment.with_user(self.drafter).write({'needs_moderation': True})
        comment.with_user(self.approver).write({'needs_moderation': True})

    def test_drafter_cannot_use_other_pages(self):
        with self.assertRaises(AccessError):
            self._post(self.drafter, self.page_a | self.page_b)

    def test_publisher_posts_and_deletes(self):
        post = self._post(self.publisher, self.page_a | self.page_b)
        with patch.object(FacebookProvider, 'publish', fake_publish):
            post.action_publish_now()
        self.assertEqual(post.state, 'posted')
        self.assertEqual(len(post.publication_ids), 2)
        # Editing a published post needs "Create and Edit Published".
        with self.assertRaises(AccessError):
            post.with_user(self.drafter).write({'message': 'changed'})
        with patch.object(FacebookProvider, 'delete_post', lambda self, publication: None):
            post.action_delete_from_platforms()
        self.assertEqual(set(post.publication_ids.mapped('state')), {'deleted'})
        with self.assertRaises(AccessError):
            self._post(self.drafter, self.page_a).with_user(self.drafter).unlink()

    def test_failed_publication(self):
        post = self._post(self.publisher, self.page_a)

        def boom(self, post, channel):
            raise UserError('Nope')
        with patch.object(FacebookProvider, 'publish', boom):
            post.action_publish_now()
        self.assertEqual(post.state, 'failed')
        self.assertIn('Nope', post.publication_ids.failure_reason)

    def test_schedule_and_cron(self):
        from datetime import timedelta
        from odoo import fields
        post = self._post(self.publisher, self.page_a,
                          scheduled_date=fields.Datetime.now() + timedelta(hours=1))
        post.action_schedule()
        self.assertEqual(post.state, 'scheduled')
        post.sudo().scheduled_date = fields.Datetime.now() - timedelta(minutes=1)
        with patch.object(FacebookProvider, 'publish', fake_publish):
            self.env['social.post']._cron_publish_scheduled()
        self.assertEqual(post.state, 'posted')

    def test_comments_metrics_and_moderation(self):
        post = self._post(self.publisher, self.page_a)
        with patch.object(FacebookProvider, 'publish', fake_publish):
            post.action_publish_now()
        comments = [
            {'external_id': 'c1', 'author_name': 'Ann', 'message': 'Love it', 'likes': 2},
            {'external_id': 'c2', 'parent_id': 'c1', 'author_name': 'Page A', 'message': 'Thanks!', 'is_own': True},
        ]
        metrics = {'likes_count': 10, 'comments_count': 2, 'shares_count': 1, 'views_count': 500}
        with patch.object(FacebookProvider, 'fetch_metrics', lambda s, p: metrics), \
                patch.object(FacebookProvider, 'fetch_comments', lambda s, p: comments):
            post.action_sync()
        self.assertEqual(post.likes_count, 10)
        self.assertEqual(post.engagement_score, 10 + 2 * 3 + 5 + 5)
        top = post.comment_ids.filtered(lambda c: c.external_id == 'c1')
        self.assertTrue(top.replied)
        self.assertEqual(top.child_ids.message, 'Thanks!')
        # Drafters may not moderate; approver on Page A also holds Moderate.
        with self.assertRaises(AccessError):
            top.with_user(self.drafter).action_mark_reviewed()
        with patch.object(FacebookProvider, 'reply_comment', lambda s, c, t: {'external_id': 'c3'}):
            top.with_user(self.approver)._send_reply('Glad you like it')
        self.assertEqual(len(top.child_ids), 2)

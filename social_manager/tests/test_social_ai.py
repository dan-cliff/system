from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.social_manager.providers.facebook import FacebookProvider

from .common import SocialCommon


@tagged('post_install', '-at_install')
class TestSocialAi(SocialCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('claude_ai_settings.api_key', 'sk-test')
        params.set_param('social_manager.ai_analysis', 'True')
        params.set_param('social_manager.ai_recommendations', 'True')
        cls.post = cls.env['social.post'].create({
            'name': 'Launch', 'message': 'New range', 'channel_ids': [(6, 0, cls.page_a.ids)]})
        with patch.object(FacebookProvider, 'publish', lambda s, p, c: {'external_id': 'x1'}):
            cls.post.action_publish_now()
        cls.comment = cls.env['social.comment'].create({
            'publication_id': cls.post.publication_ids.id, 'external_id': 'c1',
            'author_name': 'Troll', 'message': 'You are all idiots'})

    def test_analysis_flags_comment(self):
        answer = {'comments': [{'id': self.comment.id, 'sentiment': 'Negative', 'score': -0.9,
                                'needs_moderation': True, 'moderation_reason': 'Abusive',
                                'recommended_action': 'Hide', 'suggested_reply': ''}]}
        with patch('odoo.addons.social_manager.models.social_comment.ai_request_json', return_value=answer):
            result = self.comment.ai_job_analyse()
        self.assertEqual(result['type'], 'warning')
        self.assertTrue(self.comment.needs_moderation)
        self.assertEqual(self.comment.sentiment_id, self.env.ref('social_manager.sentiment_negative'))
        self.assertEqual(self.comment.ai_recommended_action, 'Hide')

    def test_analysis_respects_setting(self):
        self.env['ir.config_parameter'].sudo().set_param('social_manager.ai_analysis', 'False')
        with self.assertRaises(UserError):
            self.comment.action_ai_analyse()

    def test_job_steps_name_the_work(self):
        steps = self.comment.get_ai_job_steps('ai_job_analyse')
        self.assertIn('Claude', steps[1])
        self.assertIn('Launch', steps[0])

    def test_recommendations_create_proposals(self):
        event = self.env['social.event'].create({
            'name': 'Spring release', 'date_start': fields.Date.add(fields.Date.today(), days=10)})
        self.post.sudo().engagement_score = 50
        captured = {}

        def fake(env, prompt, **kwargs):
            captured['prompt'] = prompt
            return {'proposals': [{
                'title': 'Spring is here', 'content': 'Our spring range lands soon!',
                'channel_ids': [self.page_a.id, 999999], 'event_id': event.id,
                'suggested_date': '20/10/2026', 'rationale': 'Builds on Launch',
                'action_items': ['Take photos', 'Write link']}]}
        with patch('odoo.addons.social_manager.models.social_post.ai_request_json', side_effect=fake):
            result = self.env['social.post'].ai_job_recommend()
        self.assertEqual(result['type'], 'success')
        proposal = self.env['social.post'].search([('state', '=', 'proposed'), ('name', '=', 'Spring is here')])
        self.assertEqual(len(proposal), 1)
        self.assertEqual(proposal.channel_ids, self.page_a)
        self.assertEqual(proposal.event_id, event)
        self.assertEqual(proposal.ai_suggested_date, fields.Date.to_date('2026-10-20'))
        self.assertIn('- Take photos', proposal.ai_action_items)
        self.assertIn('Spring release', captured['prompt'])
        self.assertIn('best_performing_posts', captured['prompt'])
        self.assertIn('Launch', captured['prompt'])
        proposal.action_accept_proposal()
        self.assertEqual(proposal.state, 'draft')

    def test_rank(self):
        answer = {'ranking': [{'id': self.post.id, 'rank': 1, 'insight': 'Great image'}], 'what_works': 'Images'}
        with patch('odoo.addons.social_manager.models.social_post.ai_request_json', return_value=answer):
            self.env['social.post'].ai_job_rank()
        self.assertEqual(self.post.ai_performance_rank, 1)
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('social_manager.ai_what_works'), 'Images')

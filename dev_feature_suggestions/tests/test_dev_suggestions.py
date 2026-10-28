from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDevSuggestions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Customer Co'})
        cls.other = cls.env['res.partner'].create({'name': 'Other Co'})
        cls.critical = cls.env.ref('dev_feature_suggestions.importance_critical')
        cls.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.api_key', '')

    def _suggestion(self, **vals):
        return self.env['dev.suggestion'].create(dict({'name': 'Export to Excel'}, **vals))

    def test_votes_and_score(self):
        suggestion = self._suggestion()
        self.assertTrue(suggestion.ref.startswith('IDEA-'))
        self.assertTrue(suggestion.is_published, 'Published straight away unless reviewing first')
        suggestion._add_vote(self.customer, importance=self.critical, note='We export daily')
        suggestion._add_vote(self.other)
        self.assertEqual(suggestion.vote_count, 2)
        self.assertEqual(suggestion.score, 3 + 1)
        self.assertIn(self.customer, suggestion.message_partner_ids, 'Voters follow the suggestion')
        # Voting again updates the vote.
        suggestion._add_vote(self.other, importance=self.critical)
        self.assertEqual(suggestion.vote_count, 2)
        self.assertEqual(suggestion.score, 6)
        suggestion._remove_vote(self.other)
        self.assertEqual(suggestion.vote_count, 1)
        suggestion.action_vote()
        self.assertTrue(suggestion.voted)
        suggestion.action_vote()
        self.assertFalse(suggestion.voted)

    def test_review_first(self):
        self.env['ir.config_parameter'].sudo().set_param('dev_feature_suggestions.review_first', 'True')
        self.assertFalse(self._suggestion().is_published)

    def test_moderation_needs_permission(self):
        user = new_test_user(self.env, 'sug_editor',
                             groups='base.group_user,dev_feature_suggestions.group_dev_suggestion_edit_all')
        suggestion = self._suggestion().with_user(user)
        suggestion.name = 'Export to Excel and CSV'
        with self.assertRaises(AccessError):
            suggestion.status_id = self.env.ref('dev_feature_suggestions.status_planned')
        with self.assertRaises(AccessError):
            suggestion.official_response = '<p>Yes</p>'
        # Without moderation, their new suggestions are still published (by the app, not by them).
        mine = self.env['dev.suggestion'].with_user(user).create({'name': 'Dark mode'})
        self.assertTrue(mine.is_published)
        suggestion.vote_count  # readable
        suggestion.action_vote()
        self.assertTrue(suggestion.voted)

    def test_status_change_notifies_and_closed_status_blocks_votes(self):
        suggestion = self._suggestion()
        suggestion._add_vote(self.customer)
        before = suggestion.message_ids
        suggestion.status_id = self.env.ref('dev_feature_suggestions.status_planned')
        self.assertTrue(any('Planned' in (m.body or '') for m in suggestion.message_ids - before))
        suggestion.status_id = self.env.ref('dev_feature_suggestions.status_declined')
        with self.assertRaises(UserError):
            suggestion._add_vote(self.other)

    def test_merge(self):
        original = self._suggestion()
        duplicate = self._suggestion(name='Excel export please')
        original._add_vote(self.customer)
        duplicate._add_vote(self.customer)
        duplicate._add_vote(self.other)
        duplicate.action_merge_into(original)
        self.assertEqual(duplicate.merged_into_id, original)
        self.assertFalse(duplicate.is_published)
        self.assertEqual(original.vote_count, 2, 'Votes move across, without double counting')
        self.assertEqual(duplicate.status_id, self.env.ref('dev_feature_suggestions.status_merged'))
        # Voting on a merged suggestion votes on the original.
        third = self.env['res.partner'].create({'name': 'Third'})
        duplicate._add_vote(third)
        self.assertEqual(original.vote_count, 3)

    def test_create_feature_and_release(self):
        suggestion = self._suggestion(description='<p>Every month</p>')
        suggestion._add_vote(self.customer)
        action = suggestion.action_create_feature()
        feature = self.env['dev.feature'].browse(action['res_id'])
        self.assertEqual(feature.suggestion_ids, suggestion)
        self.assertEqual(suggestion.status_id, self.env.ref('dev_feature_suggestions.status_planned'))
        repo = self.env['dev.repository'].create({'name': 'App', 'full_name': 'acme/app'})
        release = self.env['dev.release'].create({'repository_id': repo.id})
        feature.release_id = release
        release.sudo().state = 'core'
        self.assertEqual(suggestion.released_in_id, release)
        self.assertEqual(suggestion.status_id, self.env.ref('dev_feature_suggestions.status_released'))

    def test_ai_triage(self):
        suggestion = self._suggestion()
        other = self._suggestion(name='Excel exports')
        self.assertFalse(suggestion.ai_available)
        self.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.gemini_api_key', 'g-key')
        suggestion.invalidate_recordset(['ai_available'])
        self.assertTrue(suggestion.ai_available)
        answer = {'summary': 'Customers want spreadsheets.', 'category': 'Reporting',
                  'duplicate_ids': [other.id, 999999, 'x'], 'feature_ids': []}
        with patch('odoo.addons.dev_management.models.dev_ai.ai_request_json', return_value=answer):
            suggestion.action_ai_run('suggestion_triage')
        self.assertEqual(suggestion.similar_suggestion_ids, other)
        self.assertEqual(suggestion.category_id, self.env.ref('dev_feature_suggestions.category_reporting'))
        self.assertIn('Gemini', suggestion.get_ai_job_info('suggestion_triage')['step'])


@tagged('post_install', '-at_install')
class TestFeatureRequestsWebsite(HttpCase):

    def test_forum(self):
        suggestion = self.env['dev.suggestion'].create({'name': 'Publicly visible idea'})
        hidden = self.env['dev.suggestion'].create({'name': 'Secret idea'})
        hidden.is_published = False
        response = self.url_open('/feature-requests')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Publicly visible idea', response.text)
        self.assertNotIn('Secret idea', response.text)
        self.assertEqual(self.url_open('/feature-requests/%s' % suggestion.id).status_code, 200)
        self.assertEqual(self.url_open('/feature-requests/%s' % hidden.id).status_code, 404)
        for sort in ('new', 'trending', 'discussed'):
            self.assertEqual(self.url_open('/feature-requests?sort=%s' % sort).status_code, 200)

        portal = new_test_user(self.env, 'portal_fr', groups='base.group_portal', password='portal_fr_pw')
        self.authenticate('portal_fr', 'portal_fr_pw')
        page = self.url_open('/feature-requests/new')
        self.assertEqual(page.status_code, 200)
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        response = self.url_open('/feature-requests/new', data={
            'csrf_token': csrf, 'name': 'Portal idea', 'description': 'Line one\n\nLine two'})
        self.assertEqual(response.status_code, 200)
        created = self.env['dev.suggestion'].search([('name', '=', 'Portal idea')])
        self.assertEqual(created.partner_id, portal.partner_id)
        self.assertEqual(created.vote_count, 1, 'The suggester votes for their own idea')
        self.url_open('/feature-requests/%s/vote' % suggestion.id, data={
            'csrf_token': csrf, 'importance_id': self.env.ref('dev_feature_suggestions.importance_important').id,
            'note': 'Need it'})
        self.assertEqual(suggestion.vote_ids.partner_id, portal.partner_id)
        self.assertEqual(suggestion.vote_ids.note, 'Need it')
        self.url_open('/feature-requests/%s/comment' % suggestion.id, data={'csrf_token': csrf, 'body': 'Me too <b>!</b>'})
        comment = suggestion.message_ids.filtered(lambda m: m.author_id == portal.partner_id)
        self.assertIn('&lt;b&gt;', comment.body)

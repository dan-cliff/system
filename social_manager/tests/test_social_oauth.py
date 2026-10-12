from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from odoo.tests import HttpCase, tagged

from odoo.addons.social_manager.providers.facebook import FacebookProvider
from odoo.addons.social_manager.providers.twitter import TwitterProvider


@tagged('post_install', '-at_install')
class TestSocialOAuth(HttpCase):

    def test_oauth_round_trip(self):
        platform = self.env.ref('social_manager.platform_facebook')
        platform.write({'client_id': 'my-app', 'client_secret': 'shh'})
        self.authenticate('admin', 'admin')
        response = self.url_open('/social_manager/oauth/start/%s' % platform.id, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        location = urlparse(response.headers['Location'])
        self.assertEqual(location.netloc, 'www.facebook.com')
        query = parse_qs(location.query)
        self.assertEqual(query['client_id'], ['my-app'])
        self.assertEqual(query['redirect_uri'], [platform.redirect_uri])
        self.assertIn('pages_manage_posts', query['scope'][0])
        state = query['state'][0]

        pages = [{'external_id': 'p1', 'name': 'Page One', 'access_token': 'page-token', 'follower_count': 5},
                 {'external_id': 'p2', 'name': 'Page Two', 'access_token': 'page-token-2'}]
        with patch.object(FacebookProvider, 'exchange_code', return_value={'access_token': 'user-token', 'expires_in': 3600}), \
                patch.object(FacebookProvider, 'get_account_info', return_value={'external_id': 'me1', 'name': 'Dan'}), \
                patch.object(FacebookProvider, 'discover_channels', return_value=pages):
            response = self.url_open('/social_manager/oauth/callback?state=%s&code=abc' % state, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        account = self.env['social.account'].search([('external_id', '=', 'me1')])
        self.assertEqual(account.name, 'Dan')
        self.assertEqual(account.sudo().access_token, 'user-token')
        self.assertTrue(account.token_expiry)
        self.assertEqual(account.channel_ids.mapped('name'), ['Page One', 'Page Two'])
        self.assertEqual(account.channel_ids[0].sudo().access_token, 'page-token')
        self.assertTrue(all(len(c._social_access_groups()) == 5 for c in account.channel_ids))
        # The state can't be replayed.
        response = self.url_open('/social_manager/oauth/callback?state=%s&code=abc' % state, allow_redirects=False)
        self.assertEqual(response.status_code, 400)

    def test_pkce_for_x(self):
        platform = self.env.ref('social_manager.platform_twitter')
        platform.write({'client_id': 'x-app', 'client_secret': 'shh'})
        self.authenticate('admin', 'admin')
        response = self.url_open('/social_manager/oauth/start/%s' % platform.id, allow_redirects=False)
        query = parse_qs(urlparse(response.headers['Location']).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertTrue(query['code_challenge'][0])
        captured = {}

        def exchange(self, code, redirect_uri, code_verifier=None):
            captured['verifier'] = code_verifier
            return {'access_token': 't', 'refresh_token': 'r', 'expires_in': 7200}
        with patch.object(TwitterProvider, 'exchange_code', exchange), \
                patch.object(TwitterProvider, 'get_account_info', return_value={'external_id': 'x1', 'name': '@cliffs'}), \
                patch.object(TwitterProvider, 'discover_channels', return_value=[{'external_id': 'x1', 'name': 'Cliffs'}]):
            self.url_open('/social_manager/oauth/callback?state=%s&code=abc' % query['state'][0], allow_redirects=False)
        import base64
        import hashlib
        expected = base64.urlsafe_b64encode(hashlib.sha256(captured['verifier'].encode()).digest()).decode().rstrip('=')
        self.assertEqual(expected, query['code_challenge'][0])

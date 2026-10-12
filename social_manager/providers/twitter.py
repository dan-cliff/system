import base64

from odoo.exceptions import UserError

from .base import UPLOAD_TIMEOUT, SocialProvider


class TwitterProvider(SocialProvider):
    """X (Twitter) API v2 with OAuth 2.0 (authorisation code + PKCE)."""
    code = 'twitter'
    label = 'X (Twitter)'
    default_auth_url = 'https://x.com/i/oauth2/authorize'
    default_token_url = 'https://api.x.com/2/oauth2/token'
    default_api_base_url = 'https://api.x.com/2'
    default_scopes = 'tweet.read tweet.write tweet.moderate.write users.read like.read media.write offline.access'
    developer_portal_url = 'https://developer.x.com/en/portal/dashboard'
    setup_notes = (
        'In the X developer portal, set up User authentication for your app as a "Web App, '
        'Automated App or Bot" (confidential client) with Read and write permissions, add the OAuth '
        'Redirect URI below as its Callback URI, and copy the OAuth 2.0 Client ID and Client Secret '
        'here. Each connected X account becomes one Page / Channel.'
    )
    use_pkce = True

    def _basic_auth(self):
        raw = '%s:%s' % (self.platform.client_id, self.platform.client_secret)
        return {'Authorization': 'Basic %s' % base64.b64encode(raw.encode()).decode()}

    def exchange_code(self, code, redirect_uri, code_verifier=None):
        return self._request('POST', self.platform.token_url or self.default_token_url, headers=self._basic_auth(), data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier,
            'client_id': self.platform.client_id,
        })

    def refresh_access_token(self, refresh_token):
        return self._request('POST', self.platform.token_url or self.default_token_url, headers=self._basic_auth(), data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.platform.client_id,
        })

    def _me(self, token):
        return self._request('GET', 'users/me', token=token, params={
            'user.fields': 'profile_image_url,public_metrics,username,name'}).get('data', {})

    def get_account_info(self, token):
        me = self._me(token)
        return {'external_id': me.get('id'), 'name': '@%s' % me.get('username', ''), 'image_url': me.get('profile_image_url')}

    def discover_channels(self):
        me = self._me(self._account_token())
        return [{
            'external_id': me['id'],
            'name': me.get('name') or me.get('username'),
            'username': me.get('username'),
            'url': 'https://x.com/%s' % me.get('username', ''),
            'image_url': me.get('profile_image_url'),
            'follower_count': (me.get('public_metrics') or {}).get('followers_count'),
        }]

    def check_post(self, post, channel):
        if len(self._post_text(post)) > 280:
            raise UserError('"%s" is longer than the 280 characters X allows.' % post.name)

    def _upload_media(self, attachment, token):
        """Upload an image or video with the v2 chunked media upload; returns the media id."""
        data = self._attachment_bytes(attachment)
        is_video = (attachment.mimetype or '').startswith('video/')
        init = self._request('POST', 'media/upload/initialize', token=token, json={
            'media_type': attachment.mimetype,
            'total_bytes': len(data),
            'media_category': 'tweet_video' if is_video else 'tweet_image',
        })
        media_id = init.get('data', {}).get('id')
        chunk_size = 4 * 1024 * 1024
        for index, start in enumerate(range(0, len(data), chunk_size)):
            self._request('POST', 'media/upload/%s/append' % media_id, token=token,
                          data={'segment_index': index},
                          files={'media': ('chunk', data[start:start + chunk_size], 'application/octet-stream')},
                          timeout=UPLOAD_TIMEOUT)
        final = self._request('POST', 'media/upload/%s/finalize' % media_id, token=token)
        state = (final.get('data', {}).get('processing_info') or {}).get('state')
        if state and state not in ('succeeded',):
            self._wait_processing(media_id, token)
        return media_id

    def _wait_processing(self, media_id, token, attempts=40):
        import time
        for _attempt in range(attempts):
            status = self._request('GET', 'media/upload', token=token,
                                   params={'command': 'STATUS', 'media_id': media_id})
            info = status.get('data', {}).get('processing_info') or {}
            if info.get('state') in (None, 'succeeded'):
                return
            if info.get('state') == 'failed':
                raise UserError('X could not process the media: %s' % info.get('error', {}).get('message', ''))
            time.sleep(info.get('check_after_secs') or 3)
        raise UserError('X is still processing the media - try publishing again shortly.')

    def publish(self, post, channel):
        token = channel.account_id._get_access_token()
        body = {'text': self._post_text(post)}
        media = post.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith(('image/', 'video/')))[:4]
        if media:
            body['media'] = {'media_ids': [self._upload_media(item, token) for item in media]}
        data = self._request('POST', 'tweets', token=token, json=body).get('data', {})
        return {'external_id': data.get('id'),
                'url': 'https://x.com/%s/status/%s' % (channel.external_username or 'i', data.get('id'))}

    def fetch_metrics(self, publication):
        token = publication.channel_id.account_id._get_access_token()
        data = self._request('GET', 'tweets/%s' % publication.external_id, token=token,
                             params={'tweet.fields': 'public_metrics'}).get('data', {})
        metrics = data.get('public_metrics') or {}
        return {
            'likes_count': metrics.get('like_count', 0),
            'comments_count': metrics.get('reply_count', 0),
            'shares_count': metrics.get('retweet_count', 0) + metrics.get('quote_count', 0),
            'views_count': metrics.get('impression_count', 0),
        }

    def fetch_comments(self, publication):
        token = publication.channel_id.account_id._get_access_token()
        try:
            data = self._request('GET', 'tweets/search/recent', token=token, params={
                'query': 'conversation_id:%s' % publication.external_id,
                'tweet.fields': 'author_id,created_at,public_metrics,referenced_tweets',
                'expansions': 'author_id',
                'user.fields': 'username,name',
                'max_results': 100,
            })
        except UserError:
            return []  # search needs a paid API tier; metrics still sync
        users = {u['id']: u for u in data.get('includes', {}).get('users', [])}
        own_id = publication.channel_id.external_id
        result = []
        for tweet in reversed(data.get('data', [])):
            replied_to = next((ref['id'] for ref in tweet.get('referenced_tweets', [])
                               if ref.get('type') == 'replied_to'), None)
            author = users.get(tweet.get('author_id'), {})
            result.append({
                'external_id': tweet['id'],
                'parent_id': replied_to if replied_to != publication.external_id else None,
                'author_name': '@%s' % author.get('username', 'unknown'),
                'author_id': tweet.get('author_id'),
                'message': tweet.get('text'),
                'date': self._parse_datetime(tweet.get('created_at')),
                'likes': (tweet.get('public_metrics') or {}).get('like_count', 0),
                'is_own': tweet.get('author_id') == own_id,
            })
        return result

    def reply_comment(self, comment, text):
        token = comment.channel_id.account_id._get_access_token()
        data = self._request('POST', 'tweets', token=token, json={
            'text': text, 'reply': {'in_reply_to_tweet_id': comment.external_id}}).get('data', {})
        return {'external_id': data.get('id')}

    def hide_comment(self, comment, hidden):
        token = comment.channel_id.account_id._get_access_token()
        self._request('PUT', 'tweets/%s/hidden' % comment.external_id, token=token, json={'hidden': hidden})

    def delete_comment(self, comment):
        if not comment.is_own:
            raise UserError('X only lets you delete your own replies - hide this reply instead.')
        self._request('DELETE', 'tweets/%s' % comment.external_id,
                      token=comment.channel_id.account_id._get_access_token())

    def delete_post(self, publication):
        self._request('DELETE', 'tweets/%s' % publication.external_id,
                      token=publication.channel_id.account_id._get_access_token())

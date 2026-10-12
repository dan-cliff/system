from odoo.exceptions import UserError

from .base import UPLOAD_TIMEOUT, SocialProvider

GRAPH_VERSION = 'v23.0'


class FacebookProvider(SocialProvider):
    code = 'facebook'
    label = 'Facebook'
    default_auth_url = 'https://www.facebook.com/%s/dialog/oauth' % GRAPH_VERSION
    default_token_url = 'https://graph.facebook.com/%s/oauth/access_token' % GRAPH_VERSION
    default_api_base_url = 'https://graph.facebook.com/%s' % GRAPH_VERSION
    default_scopes = ('pages_show_list pages_read_engagement pages_manage_posts '
                      'pages_manage_engagement pages_read_user_content read_insights business_management')
    scope_separator = ','
    developer_portal_url = 'https://developers.facebook.com/apps/'
    setup_notes = (
        'Create a Business app at developers.facebook.com, add the "Facebook Login for Business" '
        'product, and add the OAuth Redirect URI below to its Valid OAuth Redirect URIs. Copy the '
        'App ID and App Secret here. Every Page the signing-in user manages is imported.'
    )

    def _exchange_long_lived(self, token):
        """Swap a short-lived user token for a ~60 day one; Page tokens from it don't expire."""
        return self._request('GET', 'oauth/access_token', params={
            'grant_type': 'fb_exchange_token',
            'client_id': self.platform.client_id,
            'client_secret': self.platform.client_secret,
            'fb_exchange_token': token['access_token'],
        })

    def exchange_code(self, code, redirect_uri, code_verifier=None):
        token = self._request('GET', self.platform.token_url or self.default_token_url, params={
            'client_id': self.platform.client_id,
            'client_secret': self.platform.client_secret,
            'redirect_uri': redirect_uri,
            'code': code,
        })
        return self._exchange_long_lived(token)

    def refresh_access_token(self, refresh_token):
        raise UserError('The Facebook sign-in has expired - reconnect the account from Platforms.')

    def get_account_info(self, token):
        data = self._request('GET', 'me', token=token, params={'fields': 'id,name,picture'})
        return {
            'external_id': data.get('id'),
            'name': data.get('name'),
            'image_url': data.get('picture', {}).get('data', {}).get('url'),
        }

    def _pages(self, fields_):
        data = self._request('GET', 'me/accounts', token=self._account_token(), params={'fields': fields_, 'limit': 100})
        return data.get('data', [])

    def discover_channels(self):
        channels = []
        for page in self._pages('id,name,username,link,access_token,fan_count,picture'):
            channels.append({
                'external_id': page['id'],
                'name': page.get('name'),
                'username': page.get('username'),
                'url': page.get('link') or 'https://www.facebook.com/%s' % page['id'],
                'image_url': page.get('picture', {}).get('data', {}).get('url'),
                'follower_count': page.get('fan_count'),
                'access_token': page.get('access_token'),
            })
        return channels

    # ------------------------------------------------------------------
    def publish(self, post, channel):
        token = channel._get_access_token()
        text = post.message or ''
        images = self._images(post)
        videos = self._videos(post)
        if videos:
            video = videos[0]
            result = self._request(
                'POST', 'https://graph-video.facebook.com/%s/%s/videos' % (GRAPH_VERSION, channel.external_id),
                token=token, data={'description': self._post_text(post), 'title': post.name},
                files={'source': (video.name, self._attachment_bytes(video), video.mimetype)},
                timeout=UPLOAD_TIMEOUT)
            post_id = result.get('id')
        elif images:
            media = []
            for image in images:
                uploaded = self._request(
                    'POST', '%s/photos' % channel.external_id, token=token, data={'published': 'false'},
                    files={'source': (image.name, self._attachment_bytes(image), image.mimetype)},
                    timeout=UPLOAD_TIMEOUT)
                media.append({'media_fbid': uploaded['id']})
            data = {'message': self._post_text(post)}
            for index, item in enumerate(media):
                data['attached_media[%d]' % index] = '{"media_fbid":"%s"}' % item['media_fbid']
            post_id = self._request('POST', '%s/feed' % channel.external_id, token=token, data=data).get('id')
        else:
            data = {'message': text}
            if post.link_url:
                data['link'] = post.link_url
            post_id = self._request('POST', '%s/feed' % channel.external_id, token=token, data=data).get('id')
        return {'external_id': post_id, 'url': 'https://www.facebook.com/%s' % post_id}

    def fetch_metrics(self, publication):
        token = publication.channel_id._get_access_token()
        data = self._request('GET', publication.external_id, token=token, params={
            'fields': 'reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),'
                      'shares,likes.summary(total_count).limit(0)',
        })
        metrics = {
            'reactions_count': data.get('reactions', {}).get('summary', {}).get('total_count', 0),
            'likes_count': data.get('likes', {}).get('summary', {}).get('total_count', 0),
            'comments_count': data.get('comments', {}).get('summary', {}).get('total_count', 0),
            'shares_count': data.get('shares', {}).get('count', 0),
        }
        try:
            insights = self._request('GET', '%s/insights' % publication.external_id, token=token,
                                     params={'metric': 'post_impressions'})
            for item in insights.get('data', []):
                if item.get('name') == 'post_impressions':
                    metrics['views_count'] = (item.get('values') or [{}])[0].get('value', 0)
        except UserError:
            pass  # insights need read_insights and enough audience; metrics above still count
        return metrics

    def fetch_comments(self, publication):
        token = publication.channel_id._get_access_token()
        data = self._request('GET', '%s/comments' % publication.external_id, token=token, params={
            'fields': 'id,message,from,created_time,like_count,is_hidden,parent{id}',
            'filter': 'stream', 'order': 'chronological', 'limit': 500,
        })
        page_id = publication.channel_id.external_id
        return [{
            'external_id': c['id'],
            'parent_id': (c.get('parent') or {}).get('id'),
            'author_name': (c.get('from') or {}).get('name') or 'Facebook user',
            'author_id': (c.get('from') or {}).get('id'),
            'message': c.get('message'),
            'date': self._parse_datetime(c.get('created_time')),
            'likes': c.get('like_count', 0),
            'is_hidden': bool(c.get('is_hidden')),
            'is_own': (c.get('from') or {}).get('id') == page_id,
        } for c in data.get('data', [])]

    def reply_comment(self, comment, text):
        token = comment.channel_id._get_access_token()
        result = self._request('POST', '%s/comments' % comment.external_id, token=token, data={'message': text})
        return {'external_id': result.get('id')}

    def hide_comment(self, comment, hidden):
        token = comment.channel_id._get_access_token()
        self._request('POST', comment.external_id, token=token, data={'is_hidden': 'true' if hidden else 'false'})

    def delete_comment(self, comment):
        self._request('DELETE', comment.external_id, token=comment.channel_id._get_access_token())

    def delete_post(self, publication):
        self._request('DELETE', publication.external_id, token=publication.channel_id._get_access_token())

    def fetch_income(self, channel, date_from, date_to):
        """Daily content monetisation earnings from Page insights (Pages in the monetisation programme)."""
        token = channel._get_access_token()
        data = self._request('GET', '%s/insights' % channel.external_id, token=token, params={
            'metric': 'content_monetization_earnings',
            'period': 'day',
            'since': self._date_param(date_from),
            'until': self._date_param(date_to),
        })
        rows = []
        for metric in data.get('data', []):
            for value in metric.get('values', []):
                amount = value.get('value')
                if isinstance(amount, dict):
                    amount = amount.get('microAmount', 0) / 1_000_000.0
                day = self._parse_datetime(value.get('end_time'))
                if amount and day:
                    rows.append({
                        'ref': 'fb-%s-%s' % (channel.external_id, day.date()),
                        'date': day.date(),
                        'amount': float(amount),
                        'name': 'Facebook content monetisation earnings',
                    })
        return rows

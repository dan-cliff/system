import json

from odoo.exceptions import UserError

from .base import UPLOAD_TIMEOUT, SocialProvider


class YouTubeProvider(SocialProvider):
    """YouTube Data API v3 (and YouTube Analytics for monetisation income), Google OAuth 2.0."""
    code = 'youtube'
    label = 'YouTube'
    default_auth_url = 'https://accounts.google.com/o/oauth2/v2/auth'
    default_token_url = 'https://oauth2.googleapis.com/token'
    default_api_base_url = 'https://www.googleapis.com/youtube/v3'
    default_scopes = ('https://www.googleapis.com/auth/youtube.force-ssl '
                      'https://www.googleapis.com/auth/youtube.upload '
                      'https://www.googleapis.com/auth/yt-analytics.readonly '
                      'https://www.googleapis.com/auth/yt-analytics-monetary.readonly')
    developer_portal_url = 'https://console.cloud.google.com/apis/credentials'
    setup_notes = (
        'In Google Cloud Console enable the "YouTube Data API v3" and "YouTube Analytics API", '
        'configure the OAuth consent screen, then create an OAuth client ID of type "Web '
        'application" with the OAuth Redirect URI below as an Authorised redirect URI. Copy the '
        'Client ID and Client Secret here. Every channel the signed-in Google account manages is '
        'imported. YouTube posts are video uploads: the post title becomes the video title.'
    )

    def _extra_authorize_params(self):
        # Ask for a refresh token every time, so the connection keeps working.
        return {'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'true'}

    def get_account_info(self, token):
        info = self._request('GET', 'https://www.googleapis.com/oauth2/v3/userinfo', token=token)
        if info.get('sub'):
            return {'external_id': info['sub'], 'name': info.get('name') or info.get('email'),
                    'image_url': info.get('picture')}
        channel = (self._request('GET', 'channels', token=token, params={
            'part': 'snippet', 'mine': 'true'}).get('items') or [{}])[0]
        return {'external_id': channel.get('id'), 'name': channel.get('snippet', {}).get('title'),
                'image_url': None}

    def discover_channels(self):
        data = self._request('GET', 'channels', token=self._account_token(), params={
            'part': 'snippet,statistics', 'mine': 'true', 'maxResults': 50})
        channels = []
        for item in data.get('items', []):
            snippet = item.get('snippet', {})
            custom = snippet.get('customUrl')
            channels.append({
                'external_id': item['id'],
                'name': snippet.get('title'),
                'username': custom,
                'url': 'https://www.youtube.com/%s' % (custom or 'channel/%s' % item['id']),
                'image_url': snippet.get('thumbnails', {}).get('default', {}).get('url'),
                'follower_count': int(item.get('statistics', {}).get('subscriberCount') or 0),
            })
        return channels

    def check_post(self, post, channel):
        if not self._videos(post):
            raise UserError('YouTube posts are video uploads - add a video to "%s".' % post.name)

    def publish(self, post, channel):
        token = channel._get_access_token()
        video = self._videos(post)[0]
        data = self._attachment_bytes(video)
        metadata = {
            'snippet': {'title': post.name[:100], 'description': self._post_text(post)[:5000]},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False},
        }
        start = self._request(
            'POST', 'https://www.googleapis.com/upload/youtube/v3/videos', token=token, raw=True,
            params={'uploadType': 'resumable', 'part': 'snippet,status'},
            headers={'Content-Type': 'application/json; charset=UTF-8',
                     'X-Upload-Content-Type': video.mimetype, 'X-Upload-Content-Length': str(len(data))},
            data=json.dumps(metadata))
        upload_url = start.headers.get('Location')
        if not upload_url:
            raise UserError('YouTube did not accept the upload.')
        result = self._request('PUT', upload_url, token=token, data=data,
                               headers={'Content-Type': video.mimetype}, timeout=UPLOAD_TIMEOUT)
        video_id = result.get('id')
        return {'external_id': video_id, 'url': 'https://www.youtube.com/watch?v=%s' % video_id}

    def fetch_metrics(self, publication):
        token = publication.channel_id._get_access_token()
        data = self._request('GET', 'videos', token=token, params={'part': 'statistics', 'id': publication.external_id})
        stats = (data.get('items') or [{}])[0].get('statistics', {})
        return {
            'likes_count': int(stats.get('likeCount') or 0),
            'comments_count': int(stats.get('commentCount') or 0),
            'views_count': int(stats.get('viewCount') or 0),
        }

    def fetch_comments(self, publication):
        token = publication.channel_id._get_access_token()
        try:
            data = self._request('GET', 'commentThreads', token=token, params={
                'part': 'snippet,replies', 'videoId': publication.external_id,
                'maxResults': 100, 'textFormat': 'plainText', 'moderationStatus': 'published'})
        except UserError as exc:
            if 'disabled comments' in str(exc).lower():
                return []
            raise
        own = publication.channel_id.external_id
        result = []

        def convert(comment, parent=None):
            snippet = comment.get('snippet', {})
            return {
                'external_id': comment['id'],
                'parent_id': parent,
                'author_name': snippet.get('authorDisplayName') or 'YouTube user',
                'author_id': (snippet.get('authorChannelId') or {}).get('value'),
                'message': snippet.get('textDisplay') or snippet.get('textOriginal'),
                'date': self._parse_datetime(snippet.get('publishedAt')),
                'likes': snippet.get('likeCount', 0),
                'is_own': (snippet.get('authorChannelId') or {}).get('value') == own,
            }

        for thread in data.get('items', []):
            top = thread.get('snippet', {}).get('topLevelComment', {})
            result.append(convert(top))
            for reply in (thread.get('replies') or {}).get('comments', []):
                result.append(convert(reply, top['id']))
        return result

    def reply_comment(self, comment, text):
        token = comment.channel_id._get_access_token()
        parent = comment.parent_id.external_id if comment.parent_id else comment.external_id
        result = self._request('POST', 'comments', token=token, params={'part': 'snippet'},
                               json={'snippet': {'parentId': parent, 'textOriginal': text}})
        return {'external_id': result.get('id')}

    def hide_comment(self, comment, hidden):
        token = comment.channel_id._get_access_token()
        self._request('POST', 'comments/setModerationStatus', token=token, params={
            'id': comment.external_id, 'moderationStatus': 'heldForReview' if hidden else 'published'})

    def delete_comment(self, comment):
        token = comment.channel_id._get_access_token()
        if comment.is_own:
            self._request('DELETE', 'comments', token=token, params={'id': comment.external_id})
        else:
            self._request('POST', 'comments/setModerationStatus', token=token,
                          params={'id': comment.external_id, 'moderationStatus': 'rejected'})

    def delete_post(self, publication):
        self._request('DELETE', 'videos', token=publication.channel_id._get_access_token(),
                      params={'id': publication.external_id})

    def fetch_income(self, channel, date_from, date_to):
        """Estimated revenue per video and day from YouTube Analytics (monetised channels)."""
        token = channel._get_access_token()
        data = self._request('GET', 'https://youtubeanalytics.googleapis.com/v2/reports', token=token, params={
            'ids': 'channel==%s' % channel.external_id,
            'startDate': self._date_param(date_from),
            'endDate': self._date_param(date_to),
            'metrics': 'estimatedRevenue',
            'dimensions': 'day,video',
            'sort': 'day',
            'maxResults': 200,
        })
        headers = [h['name'] for h in data.get('columnHeaders', [])]
        rows = []
        for row in data.get('rows', []):
            values = dict(zip(headers, row))
            if not values.get('estimatedRevenue'):
                continue
            rows.append({
                'ref': 'yt-%s-%s' % (values['video'], values['day']),
                'date': values['day'],
                'amount': float(values['estimatedRevenue']),
                'name': 'YouTube estimated revenue',
                'publication_external_id': values['video'],
            })
        return rows

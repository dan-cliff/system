from odoo.exceptions import UserError

from .base import SocialProvider


class TikTokProvider(SocialProvider):
    """TikTok Login Kit + Content Posting API (v2)."""
    code = 'tiktok'
    label = 'TikTok'
    default_auth_url = 'https://www.tiktok.com/v2/auth/authorize/'
    default_token_url = 'https://open.tiktokapis.com/v2/oauth/token/'
    default_api_base_url = 'https://open.tiktokapis.com/v2'
    default_scopes = 'user.info.basic user.info.profile user.info.stats video.list video.publish video.upload'
    scope_separator = ','
    client_id_param = 'client_key'
    developer_portal_url = 'https://developers.tiktok.com/apps'
    setup_notes = (
        'Create an app at developers.tiktok.com with the Login Kit and Content Posting API '
        'products, add the OAuth Redirect URI below as a Redirect URI, verify this database\'s '
        'domain (TikTok downloads media from it), and copy the Client Key into Client ID and the '
        'Client Secret here. TikTok\'s API does not offer comment management, so comments are not '
        'synchronised; views, likes, comment and share counts are.'
    )
    supports_comments = False
    supports_delete = False

    def exchange_code(self, code, redirect_uri, code_verifier=None):
        return self._request('POST', self.platform.token_url or self.default_token_url, data={
            'client_key': self.platform.client_id,
            'client_secret': self.platform.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }, headers={'Content-Type': 'application/x-www-form-urlencoded'})

    def refresh_access_token(self, refresh_token):
        return self._request('POST', self.platform.token_url or self.default_token_url, data={
            'client_key': self.platform.client_id,
            'client_secret': self.platform.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }, headers={'Content-Type': 'application/x-www-form-urlencoded'})

    def _user(self, token):
        data = self._request('GET', 'user/info/', token=token, params={
            'fields': 'open_id,display_name,avatar_url,username,profile_deep_link,follower_count'})
        return data.get('data', {}).get('user', {})

    def get_account_info(self, token):
        user = self._user(token)
        return {'external_id': user.get('open_id'), 'name': user.get('display_name'), 'image_url': user.get('avatar_url')}

    def discover_channels(self):
        user = self._user(self._account_token())
        return [{
            'external_id': user['open_id'],
            'name': user.get('display_name') or user.get('username'),
            'username': user.get('username'),
            'url': user.get('profile_deep_link'),
            'image_url': user.get('avatar_url'),
            'follower_count': user.get('follower_count'),
        }]

    def check_post(self, post, channel):
        if not post.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith(('video/', 'image/'))):
            raise UserError('TikTok posts need a video or images - add one to "%s".' % post.name)

    def publish(self, post, channel):
        token = channel.account_id._get_access_token()
        creator = self._request('POST', 'post/publish/creator_info/query/', token=token, json={}).get('data', {})
        privacy_options = creator.get('privacy_level_options') or ['SELF_ONLY']
        privacy = 'PUBLIC_TO_EVERYONE' if 'PUBLIC_TO_EVERYONE' in privacy_options else privacy_options[0]
        videos = self._videos(post)
        if videos:
            data = self._request('POST', 'post/publish/video/init/', token=token, json={
                'post_info': {'title': self._post_text(post)[:2200], 'privacy_level': privacy},
                'source_info': {'source': 'PULL_FROM_URL', 'video_url': self._public_url(videos[0])},
            }).get('data', {})
        else:
            images = self._images(post)[:35]
            data = self._request('POST', 'post/publish/content/init/', token=token, json={
                'post_info': {'title': post.name[:90], 'description': self._post_text(post)[:4000],
                              'privacy_level': privacy},
                'source_info': {'source': 'PULL_FROM_URL', 'photo_cover_index': 0,
                                'photo_images': [self._public_url(image) for image in images]},
                'post_mode': 'DIRECT_POST',
                'media_type': 'PHOTO',
            }).get('data', {})
        publish_id = data.get('publish_id')
        # TikTok publishes asynchronously; the video id is filled in by _resolve_publish_id.
        return {'external_id': self._resolve_publish_id(publish_id, token) or publish_id,
                'url': channel.external_url}

    def _resolve_publish_id(self, publish_id, token, attempts=12):
        import time
        for _attempt in range(attempts):
            status = self._request('POST', 'post/publish/status/fetch/', token=token,
                                   json={'publish_id': publish_id}).get('data', {})
            if status.get('status') == 'PUBLISH_COMPLETE':
                ids = status.get('publicaly_available_post_id') or status.get('publicly_available_post_id') or []
                return str(ids[0]) if ids else None
            if status.get('status') == 'FAILED':
                raise UserError('TikTok could not publish the post: %s' % status.get('fail_reason', ''))
            time.sleep(5)
        return None

    def fetch_metrics(self, publication):
        if not (publication.external_id or '').isdigit():
            return {}  # still processing on TikTok
        token = publication.channel_id.account_id._get_access_token()
        data = self._request('POST', 'video/query/', token=token,
                             params={'fields': 'id,like_count,comment_count,share_count,view_count,share_url'},
                             json={'filters': {'video_ids': [publication.external_id]}})
        videos = data.get('data', {}).get('videos', [])
        if not videos:
            return {}
        video = videos[0]
        if video.get('share_url') and not publication.external_url:
            publication.external_url = video['share_url']
        return {
            'likes_count': video.get('like_count', 0),
            'comments_count': video.get('comment_count', 0),
            'shares_count': video.get('share_count', 0),
            'views_count': video.get('view_count', 0),
        }

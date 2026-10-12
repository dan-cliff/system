import time

from odoo.exceptions import UserError

from .facebook import FacebookProvider


class InstagramProvider(FacebookProvider):
    """Instagram professional accounts, through the Instagram Graph API with Facebook Login
    (each Instagram account is linked to a Facebook Page)."""
    code = 'instagram'
    label = 'Instagram'
    default_scopes = ('instagram_basic instagram_content_publish instagram_manage_comments '
                      'instagram_manage_insights pages_show_list pages_read_engagement business_management')
    setup_notes = (
        'Instagram professional (Business or Creator) accounts are reached through the Facebook '
        'Page they are linked to. Create a Business app at developers.facebook.com with the '
        '"Instagram" and "Facebook Login for Business" products, add the OAuth Redirect URI below, '
        'and copy the App ID and App Secret here. Images and videos are fetched by Instagram from '
        'this database\'s public URL, so it must be reachable from the internet.'
    )
    supports_delete = False

    def discover_channels(self):
        channels = []
        fields_ = ('name,access_token,instagram_business_account'
                   '{id,username,name,profile_picture_url,followers_count}')
        for page in self._pages(fields_):
            ig = page.get('instagram_business_account')
            if not ig:
                continue
            channels.append({
                'external_id': ig['id'],
                'name': ig.get('name') or ig.get('username'),
                'username': ig.get('username'),
                'url': 'https://www.instagram.com/%s' % ig.get('username', ''),
                'image_url': ig.get('profile_picture_url'),
                'follower_count': ig.get('followers_count'),
                'access_token': page.get('access_token'),
            })
        return channels

    def check_post(self, post, channel):
        if not post.attachment_ids:
            raise UserError('Instagram posts need an image or a video - add one to "%s".' % post.name)

    def publish(self, post, channel):
        token = channel._get_access_token()
        ig_id = channel.external_id
        caption = self._post_text(post)
        media = post.attachment_ids.filtered(
            lambda a: (a.mimetype or '').startswith(('image/', 'video/')))[:10]
        if not media:
            raise UserError('Instagram posts need an image or a video.')

        def container(attachment, carousel=False):
            data = {}
            if (attachment.mimetype or '').startswith('video/'):
                data.update({'media_type': 'REELS', 'video_url': self._public_url(attachment)})
            else:
                data['image_url'] = self._public_url(attachment)
            if carousel:
                data['is_carousel_item'] = 'true'
            else:
                data['caption'] = caption
            return self._request('POST', '%s/media' % ig_id, token=token, data=data)['id']

        if len(media) == 1:
            creation_id = container(media)
        else:
            children = [container(item, carousel=True) for item in media]
            for child in children:
                self._wait_ready(child, token)
            creation_id = self._request('POST', '%s/media' % ig_id, token=token, data={
                'media_type': 'CAROUSEL', 'children': ','.join(children), 'caption': caption})['id']
        self._wait_ready(creation_id, token)
        media_id = self._request('POST', '%s/media_publish' % ig_id, token=token,
                                 data={'creation_id': creation_id})['id']
        permalink = self._request('GET', media_id, token=token, params={'fields': 'permalink'}).get('permalink')
        return {'external_id': media_id, 'url': permalink}

    def _wait_ready(self, container_id, token, attempts=30):
        """Videos are processed asynchronously; wait until the container can be published."""
        for _attempt in range(attempts):
            status = self._request('GET', container_id, token=token, params={'fields': 'status_code'})
            code = status.get('status_code')
            if code in (None, 'FINISHED', 'PUBLISHED'):
                return
            if code in ('ERROR', 'EXPIRED'):
                raise UserError('Instagram could not process the media (%s).' % code)
            time.sleep(5)
        raise UserError('Instagram is still processing the media - try publishing again shortly.')

    def fetch_metrics(self, publication):
        token = publication.channel_id._get_access_token()
        data = self._request('GET', publication.external_id, token=token,
                             params={'fields': 'like_count,comments_count'})
        metrics = {'likes_count': data.get('like_count', 0), 'comments_count': data.get('comments_count', 0)}
        try:
            insights = self._request('GET', '%s/insights' % publication.external_id, token=token,
                                     params={'metric': 'views,shares'})
            for item in insights.get('data', []):
                value = (item.get('values') or [{}])[0].get('value', 0)
                if item.get('name') == 'views':
                    metrics['views_count'] = value
                elif item.get('name') == 'shares':
                    metrics['shares_count'] = value
        except UserError:
            pass
        return metrics

    def fetch_comments(self, publication):
        token = publication.channel_id._get_access_token()
        data = self._request('GET', '%s/comments' % publication.external_id, token=token, params={
            'fields': 'id,text,username,timestamp,like_count,hidden,from{id},'
                      'replies{id,text,username,timestamp,like_count,hidden,from{id}}',
            'limit': 100,
        })
        own_id = publication.channel_id.external_id
        result = []

        def convert(c, parent=None):
            return {
                'external_id': c['id'],
                'parent_id': parent,
                'author_name': c.get('username') or 'Instagram user',
                'author_id': (c.get('from') or {}).get('id'),
                'message': c.get('text'),
                'date': self._parse_datetime(c.get('timestamp')),
                'likes': c.get('like_count', 0),
                'is_hidden': bool(c.get('hidden')),
                'is_own': (c.get('from') or {}).get('id') == own_id,
            }

        for c in data.get('data', []):
            result.append(convert(c))
            for reply in (c.get('replies') or {}).get('data', []):
                result.append(convert(reply, c['id']))
        return result

    def reply_comment(self, comment, text):
        token = comment.channel_id._get_access_token()
        target = comment.parent_id.external_id if comment.parent_id else comment.external_id
        result = self._request('POST', '%s/replies' % target, token=token, data={'message': text})
        return {'external_id': result.get('id')}

    def hide_comment(self, comment, hidden):
        token = comment.channel_id._get_access_token()
        self._request('POST', comment.external_id, token=token, data={'hide': 'true' if hidden else 'false'})

    def delete_post(self, publication):
        raise UserError('Instagram does not allow deleting posts through its API - delete it in the Instagram app.')

    def fetch_income(self, channel, date_from, date_to):
        return []

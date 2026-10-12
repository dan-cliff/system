from urllib.parse import quote

from odoo.exceptions import UserError

from .base import UPLOAD_TIMEOUT, SocialProvider

LINKEDIN_VERSION = '202509'


class LinkedInProvider(SocialProvider):
    """LinkedIn Community Management API: the member's own profile and the organisation Pages
    they administer."""
    code = 'linkedin'
    label = 'LinkedIn'
    default_auth_url = 'https://www.linkedin.com/oauth/v2/authorization'
    default_token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
    default_api_base_url = 'https://api.linkedin.com/rest'
    default_scopes = ('openid profile w_member_social r_organization_social w_organization_social '
                      'rw_organization_admin')
    developer_portal_url = 'https://www.linkedin.com/developers/apps'
    setup_notes = (
        'Create an app at linkedin.com/developers linked to your Company Page, request the '
        '"Community Management API" and "Sign In with LinkedIn using OpenID Connect" products, '
        'add the OAuth Redirect URI below under Auth > Authorized redirect URLs, and copy the '
        'Client ID and Client Secret here. Your profile and every Page you administer are imported.'
    )

    def _headers(self, token):
        headers = super()._headers(token)
        headers.update({'LinkedIn-Version': LINKEDIN_VERSION, 'X-Restli-Protocol-Version': '2.0.0'})
        return headers

    def get_account_info(self, token):
        info = self._request('GET', 'https://api.linkedin.com/v2/userinfo', token=token)
        return {'external_id': info.get('sub'), 'name': info.get('name'), 'image_url': info.get('picture')}

    def discover_channels(self):
        token = self._account_token()
        info = self._request('GET', 'https://api.linkedin.com/v2/userinfo', token=token)
        channels = [{
            'external_id': 'urn:li:person:%s' % info['sub'],
            'name': info.get('name'),
            'image_url': info.get('picture'),
            'url': 'https://www.linkedin.com/in/',
        }]
        try:
            acls = self._request('GET', 'organizationAcls', token=token, params={
                'q': 'roleAssignee', 'role': 'ADMINISTRATOR', 'state': 'APPROVED', 'count': 100})
        except UserError:
            return channels  # no organisation scopes granted - just the member profile
        for acl in acls.get('elements', []):
            urn = acl.get('organization')
            org_id = urn.rsplit(':', 1)[-1]
            org = self._request('GET', 'organizations/%s' % org_id, token=token)
            followers = 0
            try:
                stats = self._request('GET', 'networkSizes/%s' % quote(urn, safe=''), token=token,
                                      params={'edgeType': 'COMPANY_FOLLOWED_BY_MEMBER'})
                followers = stats.get('firstDegreeSize', 0)
            except UserError:
                pass
            vanity = org.get('vanityName')
            channels.append({
                'external_id': urn,
                'name': org.get('localizedName') or vanity or urn,
                'username': vanity,
                'url': 'https://www.linkedin.com/company/%s' % (vanity or org_id),
                'follower_count': followers,
            })
        return channels

    def _upload_image(self, attachment, owner, token):
        init = self._request('POST', 'images', token=token, params={'action': 'initializeUpload'},
                             json={'initializeUploadRequest': {'owner': owner}})
        value = init.get('value', {})
        self._request('PUT', value['uploadUrl'], token=token, data=self._attachment_bytes(attachment),
                      headers={'Content-Type': attachment.mimetype or 'application/octet-stream'},
                      raw=True, timeout=UPLOAD_TIMEOUT)
        return value['image']

    def _upload_video(self, attachment, owner, token):
        data = self._attachment_bytes(attachment)
        init = self._request('POST', 'videos', token=token, params={'action': 'initializeUpload'}, json={
            'initializeUploadRequest': {'owner': owner, 'fileSizeBytes': len(data),
                                        'uploadCaptions': False, 'uploadThumbnail': False}})
        value = init.get('value', {})
        etags = []
        for instruction in value.get('uploadInstructions', []):
            part = data[instruction['firstByte']:instruction['lastByte'] + 1]
            response = self._request('PUT', instruction['uploadUrl'], data=part, raw=True,
                                     headers={'Content-Type': 'application/octet-stream'}, timeout=UPLOAD_TIMEOUT)
            etags.append(response.headers.get('etag'))
        self._request('POST', 'videos', token=token, params={'action': 'finalizeUpload'}, json={
            'finalizeUploadRequest': {'video': value['video'], 'uploadToken': value.get('uploadToken', ''),
                                      'uploadedPartIds': etags}})
        return value['video']

    def publish(self, post, channel):
        token = channel.account_id._get_access_token()
        owner = channel.external_id
        body = {
            'author': owner,
            'commentary': self._post_text(post),
            'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED',
            'isReshareDisabledByAuthor': False,
        }
        videos = self._videos(post)
        images = self._images(post)
        if videos:
            body['content'] = {'media': {'id': self._upload_video(videos[0], owner, token), 'title': post.name}}
        elif len(images) == 1:
            body['content'] = {'media': {'id': self._upload_image(images, owner, token), 'altText': post.name}}
        elif images:
            body['content'] = {'multiImage': {'images': [
                {'id': self._upload_image(image, owner, token), 'altText': post.name} for image in images[:20]]}}
        elif post.link_url:
            body['commentary'] = post.message or ''
            body['content'] = {'article': {'source': post.link_url, 'title': post.name}}
        response = self._request('POST', 'posts', token=token, json=body, raw=True)
        urn = response.headers.get('x-restli-id') or response.headers.get('x-linkedin-id')
        return {'external_id': urn, 'url': 'https://www.linkedin.com/feed/update/%s' % urn}

    def fetch_metrics(self, publication):
        token = publication.channel_id.account_id._get_access_token()
        urn = quote(publication.external_id, safe='')
        data = self._request('GET', 'socialActions/%s' % urn, token=token)
        metrics = {
            'likes_count': (data.get('likesSummary') or {}).get('totalLikes', 0),
            'comments_count': (data.get('commentsSummary') or {}).get('aggregatedTotalComments', 0),
        }
        if 'organization' in publication.channel_id.external_id:
            try:
                stats = self._request('GET', 'organizationalEntityShareStatistics', token=token, params={
                    'q': 'organizationalEntity', 'organizationalEntity': publication.channel_id.external_id,
                    'shares': 'List(%s)' % urn if 'share' in publication.external_id else None,
                    'ugcPosts': 'List(%s)' % urn if 'ugcPost' in publication.external_id else None,
                })
                totals = (stats.get('elements') or [{}])[0].get('totalShareStatistics', {})
                metrics['views_count'] = totals.get('impressionCount', 0)
                metrics['shares_count'] = totals.get('shareCount', 0)
            except UserError:
                pass
        return metrics

    def fetch_comments(self, publication):
        token = publication.channel_id.account_id._get_access_token()
        data = self._request('GET', 'socialActions/%s/comments' % quote(publication.external_id, safe=''),
                             token=token, params={'count': 100})
        own = publication.channel_id.external_id
        result = []
        for c in data.get('elements', []):
            actor = c.get('actor') or ''
            result.append({
                'external_id': c.get('commentUrn') or c.get('$URN') or c.get('id'),
                'parent_id': c.get('parentComment'),
                'author_name': c.get('actor~', {}).get('localizedName') or actor.rsplit(':', 1)[-1] or 'LinkedIn member',
                'author_id': actor,
                'message': (c.get('message') or {}).get('text'),
                'date': self._parse_datetime((c.get('created') or {}).get('time')),
                'likes': (c.get('likesSummary') or {}).get('totalLikes', 0),
                'is_own': actor == own,
            })
        return result

    def reply_comment(self, comment, text):
        token = comment.channel_id.account_id._get_access_token()
        target = comment.external_id
        body = {'actor': comment.channel_id.external_id, 'message': {'text': text}, 'parentComment': target}
        response = self._request('POST', 'socialActions/%s/comments' % quote(target, safe=''),
                                 token=token, json=body, raw=True)
        return {'external_id': response.headers.get('x-restli-id')}

    def delete_comment(self, comment):
        token = comment.channel_id.account_id._get_access_token()
        comment_id = comment.external_id.rsplit(',', 1)[-1].rstrip(')')
        self._request('DELETE', 'socialActions/%s/comments/%s' % (
            quote(comment.publication_id.external_id, safe=''), comment_id),
            token=token, params={'actor': comment.channel_id.external_id})

    def delete_post(self, publication):
        token = publication.channel_id.account_id._get_access_token()
        self._request('DELETE', 'posts/%s' % quote(publication.external_id, safe=''), token=token)

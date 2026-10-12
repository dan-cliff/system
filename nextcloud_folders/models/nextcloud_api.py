import logging
from urllib.parse import quote

import requests
from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

NEXTCLOUD_REQUEST_TIMEOUT = 20

# ir.config_parameter keys used by this module
PARAM_PREFIX = 'nextcloud_folders.'
PARAM_URL = PARAM_PREFIX + 'url'
PARAM_USERNAME = PARAM_PREFIX + 'username'
PARAM_PASSWORD = PARAM_PREFIX + 'app_password'
PARAM_ROOT_FOLDER = PARAM_PREFIX + 'root_folder'

DAV_NS = 'DAV:'
OC_NS = 'http://owncloud.org/ns'
PROPFIND_FILEID = (
    '<?xml version="1.0"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
    '<d:prop><oc:fileid/></d:prop>'
    '</d:propfind>'
)
SHARE_TYPE_PUBLIC_LINK = 3
SHARE_PERMISSION_READ = 1


class NextcloudError(Exception):
    """An error answered by the Nextcloud server (or the request to it)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        self.status = status


class NextcloudApi(models.AbstractModel):
    """WebDAV (folders) and OCS (share links) calls to the Nextcloud server,
    as the service account set in Settings."""
    _name = 'nextcloud.api'
    _description = 'Nextcloud API'

    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _base_url(self):
        return (self._get_param(PARAM_URL) or '').strip().rstrip('/')

    @api.model
    def _credentials(self):
        return ((self._get_param(PARAM_USERNAME) or '').strip(),
                (self._get_param(PARAM_PASSWORD) or '').strip())

    @api.model
    def _root_folder(self):
        """The root folder's path segments, e.g. ``['Odoo']``."""
        return [part.strip() for part in (self._get_param(PARAM_ROOT_FOLDER) or '').split('/') if part.strip()]

    @api.model
    def _is_configured(self):
        username, password = self._credentials()
        return bool(self._base_url() and username and password)

    @api.model
    def _user_error(self, error):
        return UserError(_("Nextcloud: %s", error.message))

    @api.model
    def _request(self, method, url, **kwargs):
        if not self._is_configured():
            raise NextcloudError(_(
                "Nextcloud isn't set up. Enter the server address, username and app password "
                "in Settings > General Settings > Integrations > Nextcloud Folders."))
        headers = {'OCS-APIRequest': 'true', **kwargs.pop('headers', {})}
        try:
            response = requests.request(
                method, url, auth=self._credentials(), headers=headers,
                timeout=NEXTCLOUD_REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            _logger.warning("Nextcloud request %s %s failed: %s", method, url, e)
            raise NextcloudError(_("Could not reach the Nextcloud server (%s).", e)) from e
        if response.status_code == 401:
            raise NextcloudError(_(
                "The Nextcloud username or app password was refused."), status=401)
        return response

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @api.model
    def _dav_url(self, segments):
        username = self._credentials()[0]
        path = '/'.join(quote(segment, safe='') for segment in segments)
        return f"{self._base_url()}/remote.php/dav/files/{quote(username, safe='')}/{path}"

    @api.model
    def _folder_link(self, file_id):
        """The permanent link to a folder (follows renames and moves)."""
        return f"{self._base_url()}/f/{file_id}"

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    @api.model
    def _ensure_folder(self, segments):
        """Create the folder ``segments`` (and any missing parents) and
        return its Nextcloud file id."""
        for index in range(1, len(segments) + 1):
            response = self._request('MKCOL', self._dav_url(segments[:index]))
            # 201 created; 405 already exists
            if response.status_code not in (201, 405):
                raise NextcloudError(_(
                    "Could not create the folder \"%(path)s\" (HTTP %(status)s: %(reason)s).",
                    path='/'.join(segments[:index]), status=response.status_code,
                    reason=response.reason), status=response.status_code)
        return self._get_file_id(segments)

    @api.model
    def _get_file_id(self, segments):
        response = self._request(
            'PROPFIND', self._dav_url(segments), data=PROPFIND_FILEID,
            headers={'Depth': '0', 'Content-Type': 'application/xml'})
        if response.status_code != 207:
            raise NextcloudError(_(
                "Could not read the folder \"%(path)s\" (HTTP %(status)s: %(reason)s).",
                path='/'.join(segments), status=response.status_code, reason=response.reason),
                status=response.status_code)
        try:
            tree = etree.fromstring(response.content)
        except etree.XMLSyntaxError as e:
            raise NextcloudError(_("Nextcloud sent an unreadable answer (%s).", e)) from e
        file_id = tree.findtext(f'.//{{{OC_NS}}}fileid')
        if not file_id:
            raise NextcloudError(_("Nextcloud did not return the folder's id."))
        return file_id.strip()

    @api.model
    def _ocs(self, method, endpoint, params=None, **kwargs):
        url = f"{self._base_url()}/ocs/v2.php/apps/files_sharing/api/v1/{endpoint}"
        response = self._request(method, url, params={'format': 'json', **(params or {})},
                                 headers={'Accept': 'application/json'}, **kwargs)
        try:
            payload = response.json()['ocs']
        except (ValueError, KeyError) as e:
            raise NextcloudError(_(
                "Nextcloud sent an unreadable answer (HTTP %s).", response.status_code),
                status=response.status_code) from e
        if not response.ok:
            raise NextcloudError(
                payload.get('meta', {}).get('message') or _("HTTP %s", response.status_code),
                status=response.status_code)
        return payload.get('data')

    @api.model
    def _get_public_link(self, segments):
        """The folder's read-only public share link, created if needed."""
        path = '/' + '/'.join(segments)
        shares = self._ocs('GET', 'shares', params={'path': path, 'reshares': 'false'}) or []
        for share in shares:
            if int(share.get('share_type', -1)) == SHARE_TYPE_PUBLIC_LINK and share.get('url'):
                return share['url']
        share = self._ocs('POST', 'shares', data={
            'path': path,
            'shareType': SHARE_TYPE_PUBLIC_LINK,
            'permissions': SHARE_PERMISSION_READ,
        })
        return (share or {}).get('url') or False

    @api.model
    def _test_connection(self):
        """Check the address and credentials; return the account's display name."""
        response = self._request(
            'GET', f"{self._base_url()}/ocs/v2.php/cloud/user",
            params={'format': 'json'}, headers={'Accept': 'application/json'})
        if not response.ok:
            raise NextcloudError(_(
                "The Nextcloud server answered HTTP %(status)s (%(reason)s). Check the server address.",
                status=response.status_code, reason=response.reason), status=response.status_code)
        try:
            data = response.json()['ocs']['data']
        except (ValueError, KeyError) as e:
            raise NextcloudError(_(
                "That address didn't answer like a Nextcloud server. Check the server address.")) from e
        return data.get('display-name') or data.get('displayname') or data.get('id') or ''

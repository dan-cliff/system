import json
from datetime import date
from unittest.mock import patch
from urllib.parse import unquote

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

REQUEST = 'odoo.addons.nextcloud_folders.models.nextcloud_api.requests.request'
BASE = 'https://cloud.example.com'


class FakeResponse:
    def __init__(self, status=200, data=None, content=b''):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.reason = 'OK' if self.ok else 'Error'
        self._data = data
        self.content = content or (json.dumps(data).encode() if data is not None else b'')

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeNextcloud:
    """Answers MKCOL / PROPFIND / OCS calls like a Nextcloud server."""

    def __init__(self):
        self.folders = {}
        self.shares = {}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url))
        dav = f'{BASE}/remote.php/dav/files/odoo/'
        if url.startswith(dav):
            path = unquote(url[len(dav):])
            if method == 'MKCOL':
                parent = path.rsplit('/', 1)[0] if '/' in path else ''
                if parent and parent not in self.folders:
                    return FakeResponse(409)
                if path in self.folders:
                    return FakeResponse(405)
                self.folders[path] = str(1000 + len(self.folders))
                return FakeResponse(201)
            if method == 'PROPFIND':
                if path not in self.folders:
                    return FakeResponse(404)
                xml = (
                    '<d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:response>'
                    f'<d:propstat><d:prop><oc:fileid>{self.folders[path]}</oc:fileid></d:prop>'
                    '</d:propstat></d:response></d:multistatus>')
                return FakeResponse(207, content=xml.encode())
        if url.endswith('/apps/files_sharing/api/v1/shares'):
            if method == 'GET':
                path = kwargs['params']['path']
                return FakeResponse(200, {'ocs': {'data': self.shares.get(path, [])}})
            path = kwargs['data']['path']
            share = {'share_type': 3, 'url': f'{BASE}/s/{len(self.shares) + 1}'}
            self.shares.setdefault(path, []).append(share)
            return FakeResponse(200, {'ocs': {'data': share}})
        if url.endswith('/ocs/v2.php/cloud/user'):
            return FakeResponse(200, {'ocs': {'data': {'id': 'odoo', 'display-name': 'Odoo Service'}}})
        return FakeResponse(404)


@tagged('post_install', '-at_install')
class TestNextcloudFolders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param('nextcloud_folders.url', BASE + '/')
        ICP.set_param('nextcloud_folders.username', 'odoo')
        ICP.set_param('nextcloud_folders.app_password', 'secret')
        ICP.set_param('nextcloud_folders.root_folder', 'Odoo')
        cls.Rule = cls.env['nextcloud.folder.rule']
        cls.Folder = cls.env['nextcloud.folder']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.country_model = cls.env['ir.model']._get('res.country')

    def setUp(self):
        super().setUp()
        self.server = FakeNextcloud()
        patcher = patch(REQUEST, side_effect=self.server)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _rule(self, **vals):
        return self.Rule.create({'model_id': self.partner_model.id, **vals})

    def test_button_creates_folder_and_opens_link(self):
        self._rule(folder_path='Contacts/{name}')
        partner = self.env['res.partner'].create({'name': 'Smith: A/B "Ltd"'})
        action = partner.action_nextcloud_folder()
        self.assertEqual(self.server.folders['Odoo/Contacts/Smith- A-B -Ltd-'], '1002')
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['url'], f'{BASE}/f/1002')
        folder = self.Folder.search([('res_model', '=', 'res.partner'), ('res_id', '=', partner.id)])
        self.assertEqual(folder.state, 'done')
        self.assertEqual(folder.path, 'Odoo/Contacts/Smith- A-B -Ltd-')
        if 'message_ids' in partner._fields:
            self.assertIn(f'{BASE}/f/1002', partner.message_ids[0].body)
        # a second press only opens it
        calls = len(self.server.calls)
        self.assertEqual(partner.action_nextcloud_folder()['url'], f'{BASE}/f/1002')
        self.assertEqual(len(self.server.calls), calls)

    def test_path_placeholders(self):
        rule = self._rule(folder_path='{model}/{country_id.code}/{id} {is_company}')
        partner = self.env['res.partner'].create({
            'name': 'Acme', 'is_company': True, 'country_id': self.env.ref('base.nz').id,
        })
        self.assertEqual(rule._folder_segments(partner),
                         ['Contact', 'NZ', f'{partner.id} Is a Company'])
        empty = self.env['res.partner'].create({'name': 'Nobody'})
        self.assertEqual(rule._folder_segments(empty)[1:], ['_', str(empty.id)])
        # dates are dd/mm/yyyy, with the / made safe for a folder name
        rate_rule = self.Rule.create({
            'model_id': self.env['ir.model']._get('res.currency.rate').id,
            'folder_path': 'Rates/{currency_id.name} {name}',
        })
        rate = self.env['res.currency.rate'].create({
            'currency_id': self.env.ref('base.EUR').id, 'name': date(2026, 3, 9), 'rate': 1.5,
        })
        self.assertEqual(rate_rule._folder_segments(rate), ['Rates', 'EUR 09-03-2026'])

    def test_invalid_paths(self):
        with self.assertRaises(ValidationError):
            self._rule(folder_path='{no_such_field}')
        with self.assertRaises(ValidationError):
            self._rule(folder_path='{name.code}')
        with self.assertRaises(ValidationError):
            self._rule(folder_path=' / ')

    def test_auto_create_with_filter(self):
        self._rule(folder_path='Companies/{name}', auto_create=True,
                   filter_domain="[('is_company', '=', True)]")
        company, person = self.env['res.partner'].create([
            {'name': 'Acme', 'is_company': True},
            {'name': 'Jo'},
        ])
        folders = self.Folder.search([('res_model', '=', 'res.partner')])
        self.assertEqual(folders.mapped('res_id'), [company.id])
        self.assertEqual(folders.state, 'pending')
        with patch.object(type(self.env['ir.cron']), '_commit_progress', return_value=1):
            self.Folder._cron_create_folders()
        self.assertEqual(folders.state, 'done')
        self.assertIn('Odoo/Companies/Acme', self.server.folders)
        self.assertNotIn(person.id, folders.mapped('res_id'))

    def test_create_existing_records(self):
        rule = self.Rule.create({'model_id': self.country_model.id, 'folder_path': 'Countries/{code}',
                                 'filter_domain': "[('code', 'in', ['NZ', 'AU'])]"})
        rule.action_create_existing()
        self.assertEqual(rule.folder_count, 2)
        rule.action_create_existing()
        self.assertEqual(rule.folder_count, 2)

    def test_public_link(self):
        self._rule(folder_path='Contacts/{name}', public_link=True)
        partner = self.env['res.partner'].create({'name': 'Shared'})
        partner.action_nextcloud_folder()
        folder = self.Folder.search([('res_id', '=', partner.id), ('res_model', '=', 'res.partner')])
        self.assertEqual(folder.public_url, f'{BASE}/s/1')
        # an existing public link is reused
        folder.public_url = False
        folder.action_retry()
        self.assertEqual(folder.public_url, f'{BASE}/s/1')

    @mute_logger('odoo.addons.nextcloud_folders.models.nextcloud_folder')
    def test_errors_kept_and_retried(self):
        self._rule(folder_path='Contacts/{name}', auto_create=True)
        partner = self.env['res.partner'].create({'name': 'Later'})
        folder = self.Folder.search([('res_id', '=', partner.id), ('res_model', '=', 'res.partner')])
        with patch(REQUEST, return_value=FakeResponse(500)):
            folder._create_in_nextcloud()
        self.assertEqual(folder.state, 'error')
        self.assertEqual(folder.attempt_count, 1)
        self.assertIn('HTTP 500', folder.error)
        with patch(REQUEST, return_value=FakeResponse(401)), self.assertRaises(UserError):
            partner.action_nextcloud_folder()
        folder._create_in_nextcloud()
        self.assertEqual(folder.state, 'done')
        self.assertFalse(folder.error)

    def test_no_rule_or_not_configured(self):
        partner = self.env['res.partner'].create({'name': 'No rule'})
        with self.assertRaises(UserError):
            partner.action_nextcloud_folder()
        self._rule()
        self.env['ir.config_parameter'].sudo().set_param('nextcloud_folders.app_password', False)
        with self.assertRaises(UserError), mute_logger('odoo.addons.nextcloud_folders.models.nextcloud_folder'):
            partner.action_nextcloud_folder()

    def test_folder_button_on_form(self):
        arch = self.env['res.partner'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertNotIn('action_nextcloud_folder', arch)
        rule = self._rule()
        arch = self.env['res.partner'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('action_nextcloud_folder', arch)
        # forms without a button box get one
        arch = self.env['res.country'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertNotIn('action_nextcloud_folder', arch)
        rule.active = False
        arch = self.env['res.partner'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertNotIn('action_nextcloud_folder', arch)
        self.Rule.create({'model_id': self.country_model.id, 'folder_path': '{name}'})
        arch = self.env['res.country'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('action_nextcloud_folder', arch)

    def test_settings_test_connection(self):
        settings = self.env['res.config.settings'].create({})
        action = settings.action_nextcloud_test()
        self.assertEqual(action['params']['type'], 'success')
        self.assertIn('Odoo', self.server.folders)

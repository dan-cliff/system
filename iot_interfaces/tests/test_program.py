# -*- coding: utf-8 -*-
import base64
import hashlib
import json
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.iot_program import files_digest
from .common import pair

MANIFEST = json.dumps({'entrypoint': 'main.py', 'home': '/my/page'}).encode()


class TestProgramVersions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.program = cls.env['iot.program'].create({'name': 'Custom', 'role': 'custom'})

    def test_versions_and_history(self):
        v1 = self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(1)'}, 'manual')
        self.assertEqual(v1.state, 'released')
        self.assertEqual(v1.entrypoint, 'main.py')
        self.assertEqual(v1.home_path, '/my/page')
        self.assertEqual(self.program.current_version_id, v1)
        self.assertEqual(v1.digest, files_digest({
            'iot_program.json': hashlib.sha256(MANIFEST).hexdigest(),
            'main.py': hashlib.sha256(b'print(1)').hexdigest(),
        }))
        # The same files are the same version.
        self.assertEqual(self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(1)'},
                                                      'manual'), v1)
        v2 = self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(2)'}, 'manual')
        self.assertEqual(v2.sequence, 2)
        self.assertEqual(self.program.current_version_id, v2)

        # Released files can't change; history can't be deleted.
        with self.assertRaises(UserError):
            v2.file_ids[0].data = base64.b64encode(b'changed')
        with self.assertRaises(UserError):
            v1.unlink()

        # Roll back: v1 becomes current and newer versions stop taking over.
        v1.action_make_current()
        self.assertEqual(self.program.current_version_id, v1)
        self.assertFalse(self.program.follow_latest)
        v3 = self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(3)'}, 'manual')
        self.assertEqual(self.program.current_version_id, v1)

        # A draft from a version, edited and released.
        draft = self.env['iot.program.version'].browse(v3.action_duplicate_as_draft()['res_id'])
        self.assertEqual(draft.state, 'draft')
        draft.file_ids.filtered(lambda f: f.path == 'main.py').data = base64.b64encode(b'print(4)')
        draft.action_release()
        self.assertEqual(draft.sequence, 4)
        self.assertNotEqual(draft.digest, v3.digest)

    def test_bad_manifest(self):
        version = self.env['iot.program.version'].create({
            'program_id': self.program.id,
            'file_ids': [(0, 0, {'path': 'iot_program.json',
                                 'data': base64.b64encode(b'{"entrypoint": "missing.py"}')})],
        })
        with self.assertRaises(UserError):
            version.action_release()

    def test_node_target_and_report(self):
        node = self.env['iot.node'].create({'name': 'Node'})
        self.assertEqual(node.update_state, 'none')
        v1 = self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(1)'}, 'manual')
        node.invalidate_recordset()  # the program changed (a new request in real use)
        payload = node._iot_program_payload()
        self.assertEqual(payload['digest'], v1.digest)
        self.assertEqual(payload['entrypoint'], 'main.py')
        self.assertEqual({f['path'] for f in payload['files']}, {'iot_program.json', 'main.py'})
        self.assertEqual(node.update_state, 'pending')
        node._iot_report_program({'digest': v1.digest})
        self.assertEqual(node.installed_version_id, v1)
        self.assertEqual(node.update_state, 'current')

        v2 = self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(2)'}, 'manual')
        node.invalidate_recordset()
        self.assertEqual(node.update_state, 'pending')
        node._iot_report_program({'digest': v1.digest, 'error': 'v2 kept crashing; rolled back to v1'})
        self.assertEqual(node.update_state, 'failed')
        # Pin the Node to v1.
        node.write({'update_policy': 'pinned', 'pinned_version_id': v1.id})
        self.assertEqual(node.target_version_id, v1)
        node._iot_report_program({'digest': v1.digest})
        self.assertEqual(node.update_state, 'current')
        self.assertNotEqual(node.target_version_id, v2)


class FakeResponse:
    def __init__(self, data, status=200):
        self.status_code = status
        self._data = data
        self.content = json.dumps(data).encode()
        self.text = self.content.decode()

    def json(self):
        return self._data


class TestGithubSync(TransactionCase):

    def setUp(self):
        super().setUp()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('iot_interfaces.github_enabled', 'True')
        params.set_param('iot_interfaces.github_token', 'token')
        self.program = self.env['iot.program'].create({
            'name': 'Custom', 'role': 'custom', 'github_repository': 'acme/nodes', 'github_path': 'custom',
        })
        blob = lambda data: {'content': base64.b64encode(data).decode()}  # noqa: E731
        self.blobs = {'b-manifest': blob(MANIFEST), 'b-main-1': blob(b'print(1)'), 'b-main-2': blob(b'print(2)')}
        self.trees = {
            'c1': [('custom/iot_program.json', 'b-manifest'), ('custom/main.py', 'b-main-1'), ('README.md', 'x')],
            'c2': [('custom/iot_program.json', 'b-manifest'), ('custom/main.py', 'b-main-2')],
        }
        self.commits = [self._commit('c2', 'Second'), self._commit('c1', 'First')]
        self.calls = []

    @staticmethod
    def _commit(sha, message):
        return {'sha': sha, 'html_url': 'https://github.com/acme/nodes/commit/' + sha,
                'commit': {'message': message, 'author': {'name': 'Dan', 'date': '2026-10-19T10:00:00Z'}}}

    def _fake(self, method, url, json=None, params=None, timeout=None, headers=None):
        path = url.split('api.github.com')[1]
        self.calls.append((method, path, json))
        if path == '/repos/acme/nodes/commits':
            self.assertEqual(params['path'], 'custom')
            return FakeResponse(self.commits)
        if path.startswith('/repos/acme/nodes/git/trees/'):
            sha = path.rsplit('/', 1)[1]
            return FakeResponse({'tree': [{'path': p, 'sha': s, 'type': 'blob'} for p, s in self.trees[sha]]})
        if path.startswith('/repos/acme/nodes/git/blobs/'):
            return FakeResponse(self.blobs[path.rsplit('/', 1)[1]])
        return FakeResponse({'message': 'Not Found'}, 404)

    def test_sync_keeps_history(self):
        with patch('requests.request', side_effect=self._fake):
            self.program.action_github_sync()
        versions = self.program.version_ids.sorted('sequence')
        self.assertEqual(versions.mapped('commit_sha'), ['c1', 'c2'])
        self.assertEqual(versions.mapped('source'), ['github', 'github'])
        self.assertEqual(versions[1].commit_message, 'Second')
        self.assertEqual(self.program.current_version_id, versions[1])
        self.assertEqual(self.program.github_head_sha, 'c2')
        # README.md outside the folder is not part of the program.
        self.assertEqual(set(versions[0].file_ids.mapped('path')), {'iot_program.json', 'main.py'})

        # Nothing new: no new versions, and known blobs aren't downloaded again.
        self.calls.clear()
        with patch('requests.request', side_effect=self._fake):
            self.program.action_github_sync()
        self.assertEqual(len(self.program.version_ids), 2)
        self.assertFalse([c for c in self.calls if '/git/' in c[1]])

        # A third commit.
        self.blobs['b-main-3'] = {'content': base64.b64encode(b'print(3)').decode()}
        self.trees['c3'] = [('custom/iot_program.json', 'b-manifest'), ('custom/main.py', 'b-main-3')]
        self.commits.insert(0, self._commit('c3', 'Third'))
        with patch('requests.request', side_effect=self._fake):
            self.program.action_github_sync()
        self.assertEqual(self.program.current_version_id.commit_sha, 'c3')
        self.assertEqual(len(self.program.version_ids), 3)

    def test_builtin_skipped_when_in_github(self):
        self.assertTrue(self.program.uses_github)
        with patch.object(type(self.env['iot.program']), '_iot_builtin_programs',
                          lambda self: {'custom': {'name': 'Custom', 'folder': 'iot_interfaces/tests'}}):
            self.env['iot.program']._iot_sync_builtin()
        self.assertFalse(self.program.version_ids)

    def test_publish(self):
        self.program.write({'github_repository': False})
        self.program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(1)'}, 'builtin')
        self.program.github_repository = 'acme/nodes'

        def fake(method, url, json=None, params=None, timeout=None, headers=None):
            path = url.split('api.github.com')[1]
            self.calls.append((method, path, json))
            if path == '/repos/acme/nodes/git/ref/heads/main':
                return FakeResponse({'object': {'sha': 'c0'}})
            if path == '/repos/acme/nodes/git/commits/c0':
                return FakeResponse({'tree': {'sha': 't0'}})
            if path == '/repos/acme/nodes/git/blobs' and method == 'POST':
                return FakeResponse({'sha': 'blob-%s' % len(self.calls)})
            if path == '/repos/acme/nodes/git/trees':
                return FakeResponse({'sha': 't1'})
            if path == '/repos/acme/nodes/git/commits' and method == 'POST':
                return FakeResponse({'sha': 'c1'})
            if path == '/repos/acme/nodes/git/refs/heads/main':
                return FakeResponse({'ref': 'refs/heads/main'})
            return self._fake(method, url, json, params, timeout, headers)

        with patch('requests.request', side_effect=fake):
            self.program.action_github_publish()
        tree = next(c[2] for c in self.calls if c[1] == '/repos/acme/nodes/git/trees')
        self.assertEqual(tree['base_tree'], 't0')
        self.assertEqual({e['path'] for e in tree['tree']}, {'custom/iot_program.json', 'custom/main.py'})
        commit = next(c[2] for c in self.calls if c[1] == '/repos/acme/nodes/git/commits' and c[0] == 'POST')
        self.assertEqual(commit['parents'], ['c0'])
        self.assertIn(('PATCH', '/repos/acme/nodes/git/refs/heads/main', {'sha': 'c1'}), self.calls)


@tagged('post_install', '-at_install')
class TestUpdateApi(HttpCase):

    def test_update_over_the_air(self):
        program = self.env['iot.program'].create({'name': 'Custom', 'role': 'custom'})
        version = program._create_version({'iot_program.json': MANIFEST, 'main.py': b'print(1)'}, 'manual')
        node = self.env['iot.node'].create({'name': 'Node'})
        signer = pair(node)

        def call(method, path, payload=None, with_signer=signer):
            body = json.dumps(payload).encode() if payload is not None else b''
            headers = {'Content-Type': 'application/json'}
            if with_signer:
                headers.update(with_signer.headers(method, path, body))
            self.env.invalidate_all()
            response = self.url_open(path, data=body if method == 'POST' else None, headers=headers)
            self.env.invalidate_all()
            return response

        hello = call('POST', '/iot/v1/hello', {'version': '1.0.0', 'program': {'digest': ''}}).json()
        target = hello['program']
        self.assertEqual(target['digest'], version.digest)
        main = next(f for f in target['files'] if f['path'] == 'main.py')
        self.assertEqual(call('GET', main['url']).content, b'print(1)')
        self.assertEqual(call('GET', main['url'], with_signer=None).status_code, 401)
        # Another role's Node can't download it.
        for other in self.env['iot.program'].search([('role', '!=', 'custom')]):
            try:
                with self.env.cr.savepoint():
                    other_node = self.env['iot.node'].create({'name': 'Other', 'role': other.role})
            except ValidationError:
                continue  # this role's Nodes need more settings (e.g. what a screen shows)
            other_signer = pair(other_node, mac='b8:27:eb:00:00:02')
            self.assertEqual(call('GET', main['url'], with_signer=other_signer).status_code, 404)
            break

        call('POST', '/iot/v1/hello', {'program': {'digest': version.digest}})
        self.assertEqual(node.installed_version_id, version)
        self.assertEqual(node.update_state, 'current')

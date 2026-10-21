# -*- coding: utf-8 -*-
"""The code that runs on the Nodes, with every version of it.

Each Node role has one program. A program version is a set of files plus
``iot_program.json``, which says how the Node runs them:

    {
        "entrypoint": "my_program.py",   # started and supervised by the Node agent (optional)
        "home": "/my/page",              # where the agent's local address / opens (optional)
        "setup": "setup.sh"              # run as root by the install command (optional)
    }

Versions come from the app that ships the role (built in), are uploaded in
Odoo, or - with GitHub enabled in Settings - are synced from a GitHub
repository, one version per commit. The Nodes download the version they
should run over the internet (see iot.node and the Node agent).
"""
import base64
import hashlib
import json
import logging
import os
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

MANIFEST = 'iot_program.json'
GITHUB_API = 'https://api.github.com'
GITHUB_TIMEOUT = 30
# Commits fetched per program per sync (older history comes on later syncs).
GITHUB_MAX_COMMITS = 50
SAFE_PATH = re.compile(r'^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$')


def files_digest(files):
    """One checksum for a set of files: {path: sha256}."""
    lines = ''.join('%s\0%s\n' % (path, files[path]) for path in sorted(files))
    return hashlib.sha256(lines.encode()).hexdigest()


class IotProgram(models.Model):
    _name = 'iot.program'
    _description = 'IoT Node Program'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    role = fields.Selection(selection='_selection_role', required=True, tracking=True,
                            help='The Nodes with this role run this program.')
    description = fields.Text()
    current_version_id = fields.Many2one(
        'iot.program.version', string='Current Version', tracking=True,
        domain="[('program_id', '=', id), ('state', '=', 'released')]",
        help='The version Nodes set to "Always the current version" run.',
    )
    follow_latest = fields.Boolean(
        string='Use Each New Version', default=True, tracking=True,
        help='Each newly released (or synced) version becomes the current version, so the Nodes update to it. '
             'Untick to choose the current version yourself.',
    )
    version_ids = fields.One2many('iot.program.version', 'program_id', string='Versions')
    version_count = fields.Integer(compute='_compute_counts')
    node_count = fields.Integer(compute='_compute_counts', string='Nodes')
    nodes_updated_count = fields.Integer(compute='_compute_counts', string='Nodes Up to Date')

    # ── GitHub ────────────────────────────────────────────────────────────
    github_enabled = fields.Boolean(compute='_compute_github_enabled')
    github_repository = fields.Char(string='GitHub Repository', tracking=True,
                                    help='owner/repository, e.g. dan-cliff/iot-programs.')
    github_branch = fields.Char(string='Branch', default='main', tracking=True)
    github_path = fields.Char(string='Folder', tracking=True,
                              help='Folder of the repository holding this program. Empty for the whole repository.')
    github_last_sync = fields.Datetime(string='Last Synced', readonly=True, copy=False)
    github_head_sha = fields.Char(string='Latest Commit', readonly=True, copy=False)
    github_sync_error = fields.Text(string='Sync Problem', readonly=True, copy=False)
    uses_github = fields.Boolean(compute='_compute_github_enabled',
                                 help='GitHub is enabled and this program has a repository: GitHub holds its code.')

    _role_unique = models.Constraint('UNIQUE(role)', 'Each role has one program.')

    @api.model
    def _selection_role(self):
        return self.env['iot.node']._fields['role']._description_selection(self.env)

    def _compute_counts(self):
        for program in self:
            program.version_count = len(program.version_ids)
            nodes = self.env['iot.node'].search([('role', '=', program.role)])
            program.node_count = len(nodes)
            program.nodes_updated_count = len(nodes.filtered(lambda n: n.update_state == 'current'))

    @api.depends('github_repository')
    def _compute_github_enabled(self):
        enabled = self.env['iot.github']._enabled()
        for program in self:
            program.github_enabled = enabled
            program.uses_github = enabled and bool(program.github_repository)

    @api.constrains('github_repository', 'github_path')
    def _check_github(self):
        for program in self:
            if program.github_repository and not re.match(r'^[\w.\-]+/[\w.\-]+$', program.github_repository):
                raise ValidationError(_('Write the GitHub repository as owner/repository.'))
            if program.github_path and not SAFE_PATH.match(program.github_path.strip('/')):
                raise ValidationError(_('The GitHub folder can only use letters, digits, ".", "-", "_" and "/".'))

    # ── Versions ──────────────────────────────────────────────────────────
    def _create_version(self, files, source, **vals):
        """Create and release a version from {path: bytes}. Returns it, or the
        existing version holding exactly these files."""
        self.ensure_one()
        hashes = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
        digest = files_digest(hashes)
        existing = self.version_ids.filtered(lambda v: v.digest == digest)
        if existing:
            existing = existing[0]
            if vals.get('commit_sha') and not existing.commit_sha:
                existing.write({k: v for k, v in vals.items() if k.startswith('commit_') or k == 'author_name'})
            return existing
        version = self.env['iot.program.version'].create(dict(vals, program_id=self.id, source=source, file_ids=[
            fields.Command.create({'path': path, 'data': base64.b64encode(data)})
            for path, data in sorted(files.items())
        ]))
        version.action_release()
        return version

    @api.model
    def _iot_builtin_programs(self):
        """Programs the apps ship: {role: {'name', 'description', 'folder'}}.
        ``folder`` is a module path like 'my_module/node_programs/my_role'."""
        return {}

    @api.model
    def _iot_sync_builtin(self):
        """Create a version for each shipped program whose files changed.

        Called when an app with Node programs is installed or updated.
        Programs whose code is held in GitHub are left alone.
        """
        for role, spec in self._iot_builtin_programs().items():
            program = self.with_context(active_test=False).search([('role', '=', role)], limit=1)
            if not program:
                program = self.create({'name': spec['name'], 'role': role, 'description': spec.get('description')})
            if program.uses_github:
                continue
            files = self._read_folder(spec['folder'])
            module_version = self.env['ir.module.module'].search(
                [('name', '=', spec['folder'].split('/')[0])], limit=1).latest_version
            program._create_version(files, 'builtin', notes=_('Shipped with %(module)s %(version)s',
                                                             module=spec['folder'].split('/')[0],
                                                             version=module_version or ''))

    @api.model
    def _read_folder(self, folder):
        root = file_path(folder)
        files = {}
        for directory, _dirs, names in os.walk(root):
            for name in names:
                if name.endswith(('.pyc', '.pyo')) or '__pycache__' in directory:
                    continue
                full = os.path.join(directory, name)
                with open(full, 'rb') as file:
                    files[os.path.relpath(full, root).replace(os.sep, '/')] = file.read()
        return files

    def action_view_versions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('iot_interfaces.action_iot_program_version')
        action['domain'] = [('program_id', '=', self.id)]
        action['context'] = {'default_program_id': self.id}
        return action

    def action_view_nodes(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('iot_interfaces.action_iot_node')
        action['domain'] = [('role', '=', self.role)]
        action['context'] = {'default_role': self.role}
        return action

    # ── GitHub ────────────────────────────────────────────────────────────
    def _github_folder(self):
        return (self.github_path or '').strip('/')

    def action_github_sync(self):
        github = self.env['iot.github']
        if not github._enabled():
            raise UserError(_('Turn on GitHub in IoT Interfaces > Configuration > Settings first.'))
        for program in self.filtered('github_repository'):
            try:
                program._github_sync()
            except UserError as error:
                program.github_sync_error = error.args[0]
        return True

    @api.model
    def _cron_github_sync(self):
        if not self.env['iot.github']._enabled():
            return
        for program in self.search([('github_repository', '!=', False)]):
            try:
                program._github_sync()
                self.env.cr.commit()  # keep each program's progress
            except UserError as error:
                program.github_sync_error = error.args[0]
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
                _logger.exception('IoT program %s: GitHub sync failed', program.id)

    def _github_sync(self):
        """Add a version for each commit to the program's folder that Odoo
        doesn't have yet, oldest first, so Odoo keeps the whole history."""
        self.ensure_one()
        github = self.env['iot.github']
        repo, branch, folder = self.github_repository, self.github_branch or 'main', self._github_folder()
        known = set(self.version_ids.mapped('commit_sha'))
        params = {'sha': branch, 'per_page': GITHUB_MAX_COMMITS}
        if folder:
            params['path'] = folder
        commits = github._get('/repos/%s/commits' % repo, params=params)
        new_commits = [c for c in commits if c['sha'] not in known]
        blob_cache = {f.git_sha: f for f in self.version_ids.file_ids if f.git_sha}
        for commit in reversed(new_commits):
            files, git_shas = {}, {}
            tree = github._get('/repos/%s/git/trees/%s' % (repo, commit['sha']), params={'recursive': '1'})
            prefix = folder + '/' if folder else ''
            for entry in tree.get('tree', []):
                if entry['type'] != 'blob' or not entry['path'].startswith(prefix):
                    continue
                path = entry['path'][len(prefix):]
                if entry['sha'] in blob_cache:
                    data = base64.b64decode(blob_cache[entry['sha']].with_context(bin_size=False).data or b'')
                else:
                    blob = github._get('/repos/%s/git/blobs/%s' % (repo, entry['sha']))
                    data = base64.b64decode(blob['content'])
                files[path] = data
                git_shas[path] = entry['sha']
            if not files:
                continue
            info = commit.get('commit', {})
            version = self._create_version(
                files, 'github',
                commit_sha=commit['sha'],
                commit_url=commit.get('html_url'),
                commit_message=(info.get('message') or '')[:2000],
                author_name=(info.get('author') or {}).get('name'),
                commit_date=_github_date((info.get('author') or {}).get('date')),
            )
            for file in version.file_ids:
                if not file.git_sha and git_shas.get(file.path):
                    file.sudo().git_sha = git_shas[file.path]
                    blob_cache[file.git_sha] = file
        self.write({
            'github_last_sync': fields.Datetime.now(),
            'github_head_sha': commits[0]['sha'] if commits else self.github_head_sha,
            'github_sync_error': False,
        })
        if new_commits:
            self.message_post(body=_('%s new version(s) synced from GitHub.', len(new_commits)))

    def action_github_publish(self):
        """Commit the current version's files to the program's GitHub folder,
        to start holding the program's code in GitHub."""
        self.ensure_one()
        github = self.env['iot.github']
        if not self.uses_github:
            raise UserError(_('Turn on GitHub in Settings and set the repository first.'))
        version = self.current_version_id
        if not version:
            raise UserError(_('There is no current version to publish.'))
        repo, branch, folder = self.github_repository, self.github_branch or 'main', self._github_folder()
        ref = github._get('/repos/%s/git/ref/heads/%s' % (repo, branch), allow_missing=True)
        base_commit = ref and ref['object']['sha']
        base_tree = base_commit and github._get('/repos/%s/git/commits/%s' % (repo, base_commit))['tree']['sha']
        tree = []
        for file in version.file_ids:
            blob = github._post('/repos/%s/git/blobs' % repo, {
                'content': file.with_context(bin_size=False).data.decode(), 'encoding': 'base64'})
            tree.append({'path': (folder + '/' if folder else '') + file.path, 'mode': '100644',
                         'type': 'blob', 'sha': blob['sha']})
        new_tree = github._post('/repos/%s/git/trees' % repo, dict({'tree': tree}, **(
            {'base_tree': base_tree} if base_tree else {})))
        commit = github._post('/repos/%s/git/commits' % repo, {
            'message': 'Publish %s %s from Odoo' % (self.name, version.name),
            'tree': new_tree['sha'],
            'parents': [base_commit] if base_commit else [],
        })
        if base_commit:
            github._patch('/repos/%s/git/refs/heads/%s' % (repo, branch), {'sha': commit['sha']})
        else:
            github._post('/repos/%s/git/refs' % repo, {'ref': 'refs/heads/%s' % branch, 'sha': commit['sha']})
        self.message_post(body=_('Published %(version)s to %(repo)s (%(sha)s).',
                                 version=version.name, repo=repo, sha=commit['sha'][:7]))
        self._github_sync()
        return True


def _github_date(value):
    if not value:
        return False
    return fields.Datetime.to_datetime(value.replace('T', ' ').replace('Z', ''))


class IotProgramVersion(models.Model):
    _name = 'iot.program.version'
    _description = 'IoT Node Program Version'
    _order = 'program_id, sequence desc'

    name = fields.Char(string='Version', readonly=True)
    program_id = fields.Many2one('iot.program', required=True, ondelete='cascade', index=True)
    role = fields.Selection(related='program_id.role', store=True)
    sequence = fields.Integer(readonly=True)
    # Technical states the update flow depends on.
    state = fields.Selection([('draft', 'Draft'), ('released', 'Released')], default='draft', required=True,
                             readonly=True)
    source = fields.Selection([('builtin', 'Shipped with Odoo'), ('github', 'GitHub'), ('manual', 'Uploaded')],
                              default='manual', required=True, readonly=True)
    file_ids = fields.One2many('iot.program.file', 'version_id', string='Files')
    digest = fields.Char(readonly=True, help='Checksum of all the files: the Nodes check it after downloading.')
    entrypoint = fields.Char(readonly=True, help='File the Node agent starts and keeps running.')
    home_path = fields.Char(string='Home Page', readonly=True,
                            help="Odoo page the Node's local address / opens (for screens).")
    setup_script = fields.Char(readonly=True, help='Script the install command runs as root.')
    notes = fields.Text()
    commit_sha = fields.Char(string='Commit', readonly=True, index=True)
    commit_url = fields.Char(readonly=True)
    commit_message = fields.Text(readonly=True)
    author_name = fields.Char(string='Author', readonly=True)
    commit_date = fields.Datetime(readonly=True)
    released_on = fields.Datetime(readonly=True)
    is_current = fields.Boolean(compute='_compute_is_current')
    node_count = fields.Integer(compute='_compute_node_count', string='Nodes Running It')

    def _compute_is_current(self):
        for version in self:
            version.is_current = version.program_id.current_version_id == version

    def _compute_node_count(self):
        counts = dict(self.env['iot.node']._read_group(
            [('installed_version_id', 'in', self.ids)], ['installed_version_id'], ['__count']))
        for version in self:
            version.node_count = counts.get(version, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            program = self.env['iot.program'].browse(vals['program_id'])
            last = self.search([('program_id', '=', program.id)], order='sequence desc', limit=1)
            vals['sequence'] = last.sequence + 1
            label = 'v%s' % vals['sequence']
            if vals.get('commit_sha'):
                label += ' (%s)' % vals['commit_sha'][:7]
            if not vals.get('name'):
                vals['name'] = label
        return super().create(vals_list)

    def unlink(self):
        if self.filtered(lambda v: v.state == 'released'):
            raise UserError(_('Released versions are kept as the program history and can\'t be deleted.'))
        if self.filtered('is_current'):
            raise UserError(_("The current version can't be deleted."))
        return super().unlink()

    def _manifest(self):
        self.ensure_one()
        manifest = self.file_ids.filtered(lambda f: f.path == MANIFEST)
        if not manifest:
            return {}
        try:
            data = json.loads(base64.b64decode(manifest.with_context(bin_size=False).data or b'{}'))
        except ValueError as error:
            raise UserError(_('%(file)s is not valid JSON: %(error)s', file=MANIFEST, error=error))
        return data if isinstance(data, dict) else {}

    def action_release(self):
        for version in self:
            if version.state == 'released':
                continue
            if not version.file_ids:
                raise UserError(_('Add the program files first.'))
            manifest = version._manifest()
            paths = set(version.file_ids.mapped('path'))
            for key in ('entrypoint', 'setup'):
                if manifest.get(key) and manifest[key] not in paths:
                    raise UserError(_('%(file)s names %(name)s, which is not one of the files.',
                                      file=MANIFEST, name=manifest[key]))
            version.write({
                'state': 'released',
                'released_on': fields.Datetime.now(),
                'digest': files_digest({f.path: f.sha256 for f in version.file_ids}),
                'entrypoint': manifest.get('entrypoint') or False,
                'home_path': manifest.get('home') or False,
                'setup_script': manifest.get('setup') or False,
            })
            program = version.program_id
            if program.follow_latest or not program.current_version_id:
                program.current_version_id = version
        return True

    def action_make_current(self):
        """Make this the version the Nodes run (e.g. to roll back)."""
        self.ensure_one()
        if self.state != 'released':
            raise UserError(_('Release the version first.'))
        program = self.program_id
        vals = {'current_version_id': self.id}
        newest = program.version_ids.filtered(lambda v: v.state == 'released').sorted('sequence')[-1:]
        if self != newest:
            # Rolling back: stop newer versions taking over again.
            vals['follow_latest'] = False
        program.write(vals)
        program.message_post(body=_('%(version)s made current by %(user)s: the Nodes update to it within a minute.',
                                    version=self.name, user=self.env.user.name))
        return True

    def action_duplicate_as_draft(self):
        """Start a new version from this one's files, to edit in Odoo."""
        self.ensure_one()
        draft = self.copy({'state': 'draft', 'source': 'manual', 'digest': False, 'released_on': False,
                           'commit_sha': False, 'commit_url': False,
                           'commit_message': False, 'author_name': False, 'commit_date': False,
                           'notes': _('Based on %s', self.name), 'name': False})
        for file in self.file_ids:
            file.copy({'version_id': draft.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'iot.program.version',
            'res_id': draft.id,
            'view_mode': 'form',
        }


class IotProgramFile(models.Model):
    _name = 'iot.program.file'
    _description = 'IoT Node Program File'
    _order = 'version_id, path'

    version_id = fields.Many2one('iot.program.version', required=True, ondelete='cascade', index=True)
    path = fields.Char(required=True, help='Path on the Node, relative to the program folder, e.g. my_program.py.')
    data = fields.Binary(string='File', attachment=True, required=True)
    sha256 = fields.Char(string='SHA-256', compute='_compute_sha256', store=True)
    size = fields.Integer(compute='_compute_sha256', store=True)
    git_sha = fields.Char(readonly=True)

    _path_unique = models.Constraint('UNIQUE(version_id, path)', 'Each file path appears once in a version.')

    @api.depends('data')
    def _compute_sha256(self):
        for file in self:
            raw = base64.b64decode(file.with_context(bin_size=False).data or b'')
            file.sha256 = hashlib.sha256(raw).hexdigest()
            file.size = len(raw)

    @api.constrains('path')
    def _check_path(self):
        for file in self:
            if not SAFE_PATH.match(file.path or '') or '..' in file.path.split('/'):
                raise ValidationError(_('"%s" is not a valid file path. Use letters, digits, ".", "-", "_" '
                                        'and "/" between folders.', file.path))

    def _check_editable(self):
        if self.version_id.filtered(lambda v: v.state == 'released'):
            raise UserError(_("A released version's files can't change. Use New Draft from It to change them."))

    @api.model_create_multi
    def create(self, vals_list):
        files = super().create(vals_list)
        files._check_editable()
        return files

    def write(self, vals):
        if set(vals) - {'git_sha'}:
            self._check_editable()
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        return super().unlink()

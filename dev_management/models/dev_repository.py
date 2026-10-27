"""GitHub repositories and their branches.

Each repository holds its own GitHub access token (like the IoT Interfaces
GitHub token, but per repository). Only Development Administrators can read or
set it; everything that talks to GitHub reads it with sudo().
"""
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

GITHUB_API = 'https://api.github.com'
GITHUB_WEB = 'https://github.com'
GITHUB_TIMEOUT = 30
REPO_RE = re.compile(r'^[\w.\-]+/[\w.\-]+$')
# Allowed in git ref names (and safe in API paths).
BRANCH_RE = re.compile(r'^(?!/)(?!.*//)(?!.*\.\.)[\w.\-/]+(?<!/)(?<!\.lock)$')


class DevRepository(models.Model):
    _name = 'dev.repository'
    _description = 'GitHub Repository'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True, help='How the repository is called in Odoo.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    full_name = fields.Char(
        'GitHub Repository', required=True, tracking=True,
        help='Owner and repository as on GitHub, e.g. dan-cliff/system.')
    default_branch = fields.Char(
        required=True, default='main', tracking=True,
        help='Branch new release and ticket branches start from (filled in by Test Connection).')
    description = fields.Text()
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    html_url = fields.Char('GitHub URL', compute='_compute_html_url')
    private = fields.Boolean(readonly=True, help='Private on GitHub (filled in by Test Connection).')
    github_token = fields.Char(
        'GitHub Access Token', groups='dev_management.group_dev_admin', copy=False,
        help='A fine-grained personal access token with read and write access to Contents and Pull '
             'requests on this repository.')
    token_set = fields.Boolean('Token Set', compute='_compute_token_set')
    last_check = fields.Datetime('Last Checked', readonly=True, copy=False)
    github_error = fields.Text('GitHub Problem', readonly=True, copy=False)
    branch_ids = fields.One2many('dev.branch', 'repository_id', string='Branches')
    branch_count = fields.Integer(compute='_compute_counts')
    release_ids = fields.One2many('dev.release', 'repository_id', string='Releases')
    release_count = fields.Integer(compute='_compute_counts')

    _full_name_uniq = models.Constraint('UNIQUE (full_name, company_id)',
                                        'This GitHub repository has already been added.')

    @api.depends('full_name')
    def _compute_html_url(self):
        for repo in self:
            repo.html_url = '%s/%s' % (GITHUB_WEB, repo.full_name) if repo.full_name else False

    def _compute_token_set(self):
        for repo in self:
            repo.token_set = bool(repo.sudo().github_token)

    def _compute_counts(self):
        for repo in self:
            repo.branch_count = len(repo.branch_ids)
            repo.release_count = len(repo.release_ids)

    @api.constrains('full_name', 'default_branch')
    def _check_full_name(self):
        for repo in self:
            if not REPO_RE.match(repo.full_name or ''):
                raise ValidationError(_('Write the GitHub repository as owner/repository, e.g. dan-cliff/system.'))
            if not BRANCH_RE.match(repo.default_branch or ''):
                raise ValidationError(_('"%s" is not a valid branch name.', repo.default_branch))

    @api.onchange('full_name')
    def _onchange_full_name(self):
        if self.full_name:
            self.full_name = self.full_name.strip().removeprefix(GITHUB_WEB + '/').removesuffix('.git').strip('/')
            if not self.name:
                self.name = self.full_name.split('/')[-1]

    # ── GitHub API ─────────────────────────────────────────────────────────
    def _github_request(self, method, path, payload=None, params=None, ok_statuses=()):
        """Call the GitHub REST API for this repository; ``path`` is relative to /repos/<owner>/<repo>.

        Returns (status, json). Statuses in ``ok_statuses`` are returned instead of raising.
        """
        self.ensure_one()
        token = self.sudo().github_token
        if not token:
            raise UserError(_('Set the GitHub access token on the repository %s first '
                              '(Development > Configuration > Repositories).', self.name))
        url = '%s/repos/%s%s' % (GITHUB_API, self.full_name, path)
        try:
            response = requests.request(method, url, json=payload, params=params, timeout=GITHUB_TIMEOUT, headers={
                'Authorization': 'Bearer %s' % token,
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            })
        except requests.RequestException as error:
            raise UserError(_('GitHub could not be reached: %s', error))
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {'message': response.text[:200]}
        if response.status_code >= 400 and response.status_code not in ok_statuses:
            message = data.get('message') if isinstance(data, dict) else ''
            raise UserError(_('GitHub refused %(method)s %(path)s on %(repo)s: %(status)s %(message)s',
                              method=method, path=path or '/', repo=self.full_name,
                              status=response.status_code, message=message))
        return response.status_code, data

    def _github(self, method, path, payload=None, params=None):
        return self._github_request(method, path, payload=payload, params=params)[1]

    def _github_paginate(self, path, params=None, max_pages=5):
        """All items of a list endpoint (up to max_pages of 100)."""
        items = []
        for page in range(1, max_pages + 1):
            batch = self._github('GET', path, params=dict(params or {}, per_page=100, page=page))
            if not isinstance(batch, list):
                break
            items += batch
            if len(batch) < 100:
                break
        return items

    def _github_branch_sha(self, branch):
        """SHA of the head of ``branch``, or False when it doesn't exist."""
        status, data = self._github_request('GET', '/git/ref/heads/%s' % branch, ok_statuses=(404,))
        return data.get('object', {}).get('sha') if status == 200 else False

    def _github_create_branch(self, branch, from_branch=None):
        """Create ``branch`` from ``from_branch`` (default branch); returns False when it already existed."""
        self.ensure_one()
        if not BRANCH_RE.match(branch or ''):
            raise UserError(_('"%s" is not a valid branch name.', branch))
        if self._github_branch_sha(branch):
            return False
        source = from_branch or self.default_branch
        sha = self._github_branch_sha(source)
        if not sha:
            raise UserError(_('The branch %(branch)s does not exist on %(repo)s.', branch=source, repo=self.full_name))
        self._github('POST', '/git/refs', {'ref': 'refs/heads/%s' % branch, 'sha': sha})
        return True

    def _github_tag_names(self):
        """Names of every tag and every release tag (drafts included) of the repository."""
        names = {tag.get('name') for tag in self._github_paginate('/tags')}
        names |= {rel.get('tag_name') for rel in self._github_paginate('/releases')}
        return {name for name in names if name}

    # ── Buttons ────────────────────────────────────────────────────────────
    def action_test_connection(self):
        self.ensure_one()
        try:
            data = self._github('GET', '')
        except UserError as error:
            self.write({'github_error': error.args[0], 'last_check': fields.Datetime.now()})
            raise
        self.write({
            'default_branch': data.get('default_branch') or self.default_branch,
            'private': bool(data.get('private')),
            'description': self.description or data.get('description'),
            'github_error': False,
            'last_check': fields.Datetime.now(),
        })
        return self._notify(_('Connected to %(repo)s on GitHub (default branch: %(branch)s).',
                              repo=self.full_name, branch=self.default_branch))

    def action_sync_branches(self):
        """Add every GitHub branch of the repository to Odoo, and archive the ones deleted on GitHub."""
        Branch = self.env['dev.branch']
        for repo in self:
            remote = {item['name']: item for item in repo._github_paginate('/branches', max_pages=10)}
            known = Branch.with_context(active_test=False).search([('repository_id', '=', repo.id)])
            by_name = {branch.name: branch for branch in known}
            for name, item in remote.items():
                vals = {'exists_on_github': True, 'last_commit_sha': item.get('commit', {}).get('sha'), 'active': True}
                if name in by_name:
                    by_name[name].write(vals)
                else:
                    Branch.create(dict(vals, name=name, repository_id=repo.id))
            known.filtered(lambda b: b.name not in remote and b.exists_on_github).write({'exists_on_github': False})
            repo.write({'github_error': False, 'last_check': fields.Datetime.now()})
        return self._notify(_('Branches synced from GitHub.'))

    def action_open_branches(self):
        return self._open_related('dev.branch', _('Branches'))

    def action_open_releases(self):
        return self._open_related('dev.release', _('Releases'))

    def _open_related(self, model, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list,form',
            'domain': [('repository_id', '=', self.id)],
            'context': {'default_repository_id': self.id},
        }

    def _notify(self, message, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': kind, 'message': message, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }


class DevBranch(models.Model):
    _name = 'dev.branch'
    _description = 'GitHub Branch'
    _order = 'repository_id, name'

    name = fields.Char('Branch', required=True, index=True)
    repository_id = fields.Many2one('dev.repository', required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True)
    html_url = fields.Char('GitHub URL', compute='_compute_html_url')
    ticket_ids = fields.Many2many('dev.ticket', 'dev_branch_ticket_rel', 'branch_id', 'ticket_id', string='Tickets')
    feature_ids = fields.Many2many('dev.feature', 'dev_branch_feature_rel', 'branch_id', 'feature_id',
                                   string='Features')
    release_ids = fields.Many2many('dev.release', compute='_compute_release_ids', string='Releases')
    exists_on_github = fields.Boolean('On GitHub', readonly=True)
    last_commit_sha = fields.Char('Latest Commit', readonly=True)
    pr_number = fields.Integer('Pull Request', readonly=True)
    pr_url = fields.Char('Pull Request URL', readonly=True)
    pr_state = fields.Char('Pull Request Status', readonly=True)
    merge_state = fields.Selection([
        ('merged', 'Merged'),
        ('up_to_date', 'Nothing to Merge'),
        ('conflict', 'Conflict'),
        ('missing', 'Not on GitHub'),
        ('failed', 'Failed'),
    ], 'Release Merge', readonly=True, copy=False,
        help='Result of the last "Merge Branches" of a release this branch belongs to.')
    merge_message = fields.Char('Merge Details', readonly=True, copy=False)
    merged_release_id = fields.Many2one('dev.release', 'Merged Into', readonly=True, copy=False)
    company_id = fields.Many2one(related='repository_id.company_id', store=True)

    _name_repo_uniq = models.Constraint('UNIQUE (repository_id, name)',
                                        'This branch has already been added for this repository.')

    @api.depends('name', 'repository_id.html_url')
    def _compute_html_url(self):
        for branch in self:
            branch.html_url = ('%s/tree/%s' % (branch.repository_id.html_url, branch.name)
                               if branch.repository_id.html_url and branch.name else False)

    @api.depends('ticket_ids.release_id', 'feature_ids.release_id')
    def _compute_release_ids(self):
        for branch in self:
            branch.release_ids = branch.ticket_ids.release_id | branch.feature_ids.release_id

    @api.depends('name', 'repository_id')
    def _compute_display_name(self):
        for branch in self:
            if self.env.context.get('dev_branch_show_repository') and branch.repository_id:
                branch.display_name = '%s: %s' % (branch.repository_id.name, branch.name)
            else:
                branch.display_name = branch.name

    @api.constrains('name')
    def _check_name(self):
        for branch in self:
            if not BRANCH_RE.match(branch.name or ''):
                raise ValidationError(_('"%s" is not a valid branch name.', branch.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].strip()
        return super().create(vals_list)

    def action_sync(self):
        """Refresh the branch's latest commit and pull request from GitHub."""
        for branch in self:
            repo = branch.repository_id
            sha = repo._github_branch_sha(branch.name)
            vals = {'exists_on_github': bool(sha), 'last_commit_sha': sha or False}
            owner = repo.full_name.split('/')[0]
            pulls = repo._github('GET', '/pulls', params={'head': '%s:%s' % (owner, branch.name), 'state': 'all',
                                                           'per_page': 1})
            if pulls:
                pull = pulls[0]
                state = 'merged' if pull.get('merged_at') else ('draft' if pull.get('draft') else pull.get('state'))
                vals.update(pr_number=pull.get('number'), pr_url=pull.get('html_url'), pr_state=state)
            branch.write(vals)
        return True

    def action_create_on_github(self):
        for branch in self:
            branch.repository_id._github_create_branch(branch.name)
            branch.exists_on_github = True
        return True

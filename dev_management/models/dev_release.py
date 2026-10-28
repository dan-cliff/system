"""Software releases.

A release is a two-week sprint followed by its Alpha, Beta and Core releases.
Its number is YYYY.MM.NNN (the NNNth release of that month in its repository,
counted from the release tags on GitHub and the releases in Odoo), and a draft
release is opened on GitHub as soon as it is created. When it reaches Review
the next release of the cycle is created.
"""
import logging
import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

STATES = [
    ('draft', 'Draft'),
    ('open', 'Open'),
    ('documentation', 'Documentation'),
    ('review', 'Review'),
    ('complete', 'Complete'),
    ('alpha', 'Alpha Release'),
    ('beta', 'Beta Release'),
    ('core', 'Core Release'),
    ('closed', 'Closed'),
    ('cancelled', 'Cancelled'),
]
WORKFLOW = [key for key, _label in STATES if key != 'cancelled']
# Moving a release into these needs the "Releases: Ship" permission.
SHIP_STATES = {'alpha', 'beta', 'core', 'closed'}
VERSION_RE = re.compile(r'^v?(\d{4})\.(\d{2})\.(\d+)$')

# Settings (days); see res_config_settings.py.
PARAM_PROMPT = 'dev_management.release_name_prompt'
DEFAULT_DAYS = {
    'sprint_days': 14,  # Start Date (a Monday) to End Date (the second Sunday after it), inclusive
    'alpha_days': 14,   # End Date to Alpha Release
    'beta_days': 7,     # Alpha Release to Beta Release
    'core_days': 14,    # Beta Release to Core Release
}


def first_monday(day):
    """``day`` when it is a Monday, else the Monday after it."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


class DevRelease(models.Model):
    _name = 'dev.release'
    _description = 'Release'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dev.ai.mixin']
    _order = 'date_start desc, id desc'
    _rec_names_search = ['name', 'version']
    _dev_ai_jobs = ('release_name', 'release_notes')

    name = fields.Char(tracking=True, help='Named automatically when a naming prompt is set in Settings.')
    version = fields.Char(
        'Release Number', tracking=True, copy=False, index=True,
        help='YYYY.MM.NNN: the NNNth release of the month, counted from the release tags on GitHub and the '
             'releases in Odoo. Set automatically when the release is created; you can overwrite it.')
    trivia = fields.Text(help='Key facts about whatever the release is named after.')
    ai_name_state = fields.Selection([
        ('pending', 'Naming Queued'),
        ('done', 'Named by AI'),
        ('failed', 'Naming Failed'),
    ], 'AI Naming', readonly=True, copy=False)
    ai_name_error = fields.Char('AI Naming Problem', readonly=True, copy=False)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    state = fields.Selection(STATES, 'Status', default='draft', required=True, tracking=True, copy=False,
                             index=True, group_expand=True)
    repository_id = fields.Many2one('dev.repository', 'Repository', required=True, tracking=True,
                                    ondelete='restrict', index=True)
    user_id = fields.Many2one('res.users', 'Release Manager', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    description = fields.Html('Goals', help='What this release sets out to achieve.')
    release_notes = fields.Html(copy=False)

    # ── Dates ──────────────────────────────────────────────────────────────
    date_start = fields.Date('Start Date', default=lambda self: first_monday(fields.Date.context_today(self)),
                             required=True, tracking=True, copy=False)
    date_end = fields.Date('End Date', compute='_compute_date_end', store=True, readonly=False, tracking=True,
                           copy=False)
    date_alpha = fields.Date('Alpha Release Date', compute='_compute_date_alpha', store=True, readonly=False,
                             tracking=True, copy=False)
    date_beta = fields.Date('Beta Release Date', compute='_compute_date_beta', store=True, readonly=False,
                            tracking=True, copy=False)
    date_core = fields.Date('Core Release Date', compute='_compute_date_core', store=True, readonly=False,
                            tracking=True, copy=False)
    date_closed = fields.Date('Date Closed', readonly=True, copy=False, tracking=True)

    # ── Contents ───────────────────────────────────────────────────────────
    ticket_ids = fields.One2many('dev.ticket', 'release_id', string='Tickets')
    feature_ids = fields.One2many('dev.feature', 'release_id', string='Features')
    page_ids = fields.One2many('dev.page', 'release_id', string='Documentation')
    branch_ids = fields.Many2many('dev.branch', compute='_compute_branch_ids', string='Branches',
                                  help='Branches of the tickets and features in this release, on its repository.')
    ticket_count = fields.Integer('Ticket Count', compute='_compute_progress')
    ticket_done_count = fields.Integer('Tickets Done', compute='_compute_progress')
    feature_count = fields.Integer('Feature Count', compute='_compute_progress')
    page_count = fields.Integer('Page Count', compute='_compute_progress')
    branch_count = fields.Integer('Branch Count', compute='_compute_branch_ids')
    points_total = fields.Float('Story Points', compute='_compute_progress')
    points_done = fields.Float('Story Points Done', compute='_compute_progress')
    progress = fields.Float('Progress (%)', compute='_compute_progress',
                            help='Share of the story points (or tickets, when none are estimated) that are done.')
    previous_release_id = fields.Many2one('dev.release', 'Previous Release', readonly=True, copy=False,
                                          index='btree_not_null')
    next_release_ids = fields.One2many('dev.release', 'previous_release_id', string='Following Releases')
    next_release_id = fields.Many2one('dev.release', 'Next Release', compute='_compute_next_release_id')

    # ── GitHub ─────────────────────────────────────────────────────────────
    release_branch = fields.Char('Release Branch', compute='_compute_release_branch',
                                 help='Branch the release\'s branches are merged into on GitHub.')
    release_branch_created = fields.Boolean(readonly=True, copy=False)
    github_release_id = fields.Integer('GitHub Release ID', readonly=True, copy=False)
    github_release_url = fields.Char('GitHub Release', readonly=True, copy=False)
    github_published = fields.Boolean('Published on GitHub', readonly=True, copy=False)
    github_error = fields.Text('GitHub Problem', readonly=True, copy=False)
    repository_token_set = fields.Boolean(related='repository_id.token_set')
    can_ship = fields.Boolean(compute='_compute_can_ship')

    _version_uniq = models.Constraint('UNIQUE (repository_id, version)',
                                      'Another release of this repository already has this release number.')

    # ── Computes ───────────────────────────────────────────────────────────
    @api.model
    def _days(self, key):
        value = self.env['ir.config_parameter'].sudo().get_param('dev_management.%s' % key)
        try:
            return int(value) if value not in (None, False, '') else DEFAULT_DAYS[key]
        except ValueError:
            return DEFAULT_DAYS[key]

    @api.depends('date_start')
    def _compute_date_end(self):
        days = self._days('sprint_days')
        for release in self:
            release.date_end = release.date_start and release.date_start + timedelta(days=max(days - 1, 0))

    @api.depends('date_end')
    def _compute_date_alpha(self):
        days = self._days('alpha_days')
        for release in self:
            release.date_alpha = release.date_end and release.date_end + timedelta(days=days)

    @api.depends('date_alpha')
    def _compute_date_beta(self):
        days = self._days('beta_days')
        for release in self:
            release.date_beta = release.date_alpha and release.date_alpha + timedelta(days=days)

    @api.depends('date_beta')
    def _compute_date_core(self):
        days = self._days('core_days')
        for release in self:
            release.date_core = release.date_beta and release.date_beta + timedelta(days=days)

    @api.depends('version')
    def _compute_release_branch(self):
        for release in self:
            release.release_branch = 'release/%s' % release.version if release.version else False

    @api.depends('ticket_ids.branch_ids', 'feature_ids.branch_ids', 'repository_id')
    def _compute_branch_ids(self):
        for release in self:
            branches = release.ticket_ids.branch_ids | release.feature_ids.branch_ids
            release.branch_ids = branches.filtered(lambda b: b.repository_id == release.repository_id)
            release.branch_count = len(release.branch_ids)

    @api.depends('ticket_ids.is_closed', 'ticket_ids.story_points', 'feature_ids', 'page_ids')
    def _compute_progress(self):
        for release in self:
            tickets = release.ticket_ids
            done = tickets.filtered('is_closed')
            release.ticket_count = len(tickets)
            release.ticket_done_count = len(done)
            release.feature_count = len(release.feature_ids)
            release.page_count = len(release.page_ids)
            release.points_total = sum(tickets.mapped('story_points'))
            release.points_done = sum(done.mapped('story_points'))
            if release.points_total:
                release.progress = 100.0 * release.points_done / release.points_total
            else:
                release.progress = 100.0 * len(done) / len(tickets) if tickets else 0.0

    @api.depends('next_release_ids')
    def _compute_next_release_id(self):
        for release in self:
            release.next_release_id = release.next_release_ids[:1]

    def _compute_can_ship(self):
        can_ship = self.env.user.has_group('dev_management.group_dev_release_ship')
        for release in self:
            release.can_ship = can_ship

    @api.depends('name', 'version')
    def _compute_display_name(self):
        for release in self:
            if release.version and release.name and release.name != release.version:
                release.display_name = '%s %s' % (release.version, release.name)
            else:
                release.display_name = release.name or release.version or _('New Release')

    # ── Release numbers ────────────────────────────────────────────────────
    @api.model
    def _next_version(self, repository, day=None, taken=()):
        """Next YYYY.MM.NNN for ``repository`` in the month of ``day`` (today by default)."""
        day = day or fields.Date.context_today(self)
        prefix = day.strftime('%Y.%m.')
        names = set(taken)
        names.update(self.with_context(active_test=False).search([
            ('repository_id', '=', repository.id), ('version', '=like', prefix + '%'),
        ]).mapped('version'))
        if repository.sudo().github_token:
            try:
                names |= repository._github_tag_names()
            except UserError as error:
                _logger.warning('Could not read the release tags of %s from GitHub: %s', repository.full_name, error)
        numbers = [0]
        for name in names:
            match = VERSION_RE.match(name or '')
            if match and int(match.group(1)) == day.year and int(match.group(2)) == day.month:
                numbers.append(int(match.group(3)))
        return '%s%03d' % (prefix, max(numbers) + 1)

    def action_recompute_version(self):
        """Work the release number out again from GitHub and the other releases."""
        for release in self:
            release.version = False
            release.version = self._next_version(release.repository_id)
        return True

    # ── CRUD ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        prompt = self._name_prompt()
        ai_ready = bool(prompt) and self.env['dev.ai']._available()
        taken = {}
        for vals in vals_list:
            if vals.get('repository_id') and not vals.get('version'):
                repository = self.env['dev.repository'].browse(vals['repository_id'])
                version = self._next_version(repository, taken=taken.setdefault(repository.id, set()))
                taken[repository.id].add(version)
                vals['version'] = version
            if not vals.get('name'):
                vals['name'] = vals.get('version') or _('New Release')
                if ai_ready:
                    vals['ai_name_state'] = 'pending'
        releases = super().create(vals_list)
        if releases.filtered(lambda r: r.ai_name_state == 'pending'):
            self._trigger_ai_naming()
        releases._github_create_drafts()
        return releases

    def write(self, vals):
        if vals.get('state'):
            self._check_state_change(vals['state'])
            if vals['state'] == 'closed':
                vals.setdefault('date_closed', fields.Date.context_today(self))
            elif 'date_closed' not in vals:
                vals['date_closed'] = False
        result = super().write(vals)
        if vals.get('state') == 'review':
            for release in self.filtered(lambda r: not r.next_release_id):
                release._create_next_release()
        if vals.get('state') == 'documentation':
            self.filtered(lambda r: not r.release_notes)._fill_release_notes()
        if {'name', 'version', 'release_notes'} & set(vals):
            self.filtered('github_release_id')._github_update_release(raise_errors=False)
        return result

    def _check_state_change(self, state):
        if state in SHIP_STATES and not self.env.su and not self.env.user.has_group(
                'dev_management.group_dev_release_ship'):
            raise AccessError(_('Only users with the "Releases: Ship" permission can move a release into '
                                'Alpha, Beta or Core Release, or close it.'))

    def _create_next_release(self):
        """Create the release that follows this one in the cycle (when it reaches Review)."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        start = first_monday(today)
        if self.date_end:
            start = max(start, first_monday(self.date_end + timedelta(days=1)))
        return self.sudo().create({
            'repository_id': self.repository_id.id,
            'company_id': self.company_id.id,
            'user_id': self.user_id.id,
            'date_start': start,
            'previous_release_id': self.id,
        })

    # ── Workflow ───────────────────────────────────────────────────────────
    def action_advance(self):
        """Move the release on to the next status of the workflow."""
        for release in self:
            if release.state in ('closed', 'cancelled'):
                continue
            release.state = WORKFLOW[WORKFLOW.index(release.state) + 1]
        return True

    def action_back(self):
        for release in self:
            if release.state in ('draft', 'cancelled'):
                continue
            release.state = WORKFLOW[WORKFLOW.index(release.state) - 1]
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_open_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(domain=[('release_id', '=', self.id)], context={
            'default_release_id': self.id, 'default_repository_id': self.repository_id.id})
        return action

    def action_open_features(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_feature_action')
        action.update(domain=[('release_id', '=', self.id)], context={
            'default_release_id': self.id, 'default_repository_id': self.repository_id.id})
        return action

    def action_open_pages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_page_action')
        action.update(domain=[('release_id', '=', self.id)], context={'default_release_id': self.id})
        return action

    def action_move_open_tickets(self):
        """Move the release's unfinished tickets into the next release (creating it when needed)."""
        self.ensure_one()
        target = self.next_release_id or self._create_next_release()
        open_tickets = self.ticket_ids.filtered(lambda t: not t.is_closed)
        open_tickets.write({'release_id': target.id})
        self.message_post(body=_('%(count)s unfinished ticket(s) moved to %(release)s.',
                                 count=len(open_tickets), release=target.display_name))
        return self.repository_id._notify(_('%(count)s unfinished ticket(s) moved to %(release)s.',
                                            count=len(open_tickets), release=target.display_name))

    def action_open_github_release(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.github_release_url, 'target': 'new'}

    def action_open_next_release(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.release', 'res_id': self.next_release_id.id,
                'view_mode': 'form'}

    # ── Release notes ──────────────────────────────────────────────────────
    def _release_notes_html(self):
        """Release notes listing the release's features and tickets, by ticket type."""
        self.ensure_one()
        parts = []
        if self.feature_ids:
            parts.append(Markup('<h3>%s</h3><ul>%s</ul>') % (_('Features'), Markup('').join(
                Markup('<li><strong>%s</strong> %s</li>') % (f.key or '', f.name) for f in self.feature_ids)))
        tickets = self.ticket_ids
        for ticket_type in tickets.type_id.sorted('sequence'):
            of_type = tickets.filtered(lambda t: t.type_id == ticket_type)
            parts.append(Markup('<h3>%s</h3><ul>%s</ul>') % (ticket_type.name, Markup('').join(
                Markup('<li><strong>%s</strong> %s</li>') % (t.key or '', t.name) for t in of_type)))
        untyped = tickets.filtered(lambda t: not t.type_id)
        if untyped:
            parts.append(Markup('<h3>%s</h3><ul>%s</ul>') % (_('Other Changes'), Markup('').join(
                Markup('<li><strong>%s</strong> %s</li>') % (t.key or '', t.name) for t in untyped)))
        return Markup('').join(parts) or Markup('<p>%s</p>') % _('No tickets or features yet.')

    def _fill_release_notes(self):
        for release in self:
            release.release_notes = release._release_notes_html()

    def action_generate_release_notes(self):
        self._fill_release_notes()
        return True

    # ── GitHub ─────────────────────────────────────────────────────────────
    def _github_payload(self, draft=None):
        self.ensure_one()
        title = self.version if self.name in (False, self.version) else '%s %s' % (self.version, self.name)
        payload = {'name': title, 'body': html2plaintext(self.release_notes or self.description or '') or ''}
        if not self.github_published:
            payload['tag_name'] = self.version
            payload['target_commitish'] = (self.release_branch if self.release_branch_created
                                           else self.repository_id.default_branch)
        if draft is not None:
            payload['draft'] = draft
        return payload

    def _github_create_drafts(self):
        """Open a draft release on GitHub for each release whose repository has a token."""
        for release in self.filtered(lambda r: r.version and r.repository_id.sudo().github_token
                                     and not r.github_release_id):
            try:
                release._github_create_draft()
            except UserError as error:
                release.github_error = error.args[0]
                release.message_post(body=_('The draft release could not be created on GitHub: %s', error.args[0]))

    def _github_create_draft(self):
        self.ensure_one()
        data = self.repository_id._github('POST', '/releases', self._github_payload(draft=True))
        self.sudo().write({'github_release_id': data.get('id'), 'github_release_url': data.get('html_url'),
                           'github_error': False})

    def _github_update_release(self, raise_errors=True):
        # Releases whose repository has lost its token are left alone (nothing to update on GitHub with).
        for release in self.filtered(lambda r: r.github_release_id and r.repository_id._github_ready()):
            try:
                release.repository_id._github('PATCH', '/releases/%s' % release.github_release_id,
                                              release._github_payload())
                if release.github_error:
                    release.github_error = False
            except UserError as error:
                if raise_errors:
                    raise
                release.github_error = error.args[0]

    def action_github_create_release(self):
        cancelled = self.repository_id._github_guard(_('Create Draft on GitHub'))
        if cancelled:
            return cancelled
        for release in self:
            if release.github_release_id:
                release._github_update_release()
            else:
                release._github_create_draft()
        return True

    def action_github_update_release(self):
        cancelled = self.repository_id._github_guard(_('Update GitHub Release'))
        if cancelled:
            return cancelled
        self._github_update_release()
        return self.repository_id._notify(_('The GitHub release has been updated.'))

    def _check_ship(self):
        if not self.env.user.has_group('dev_management.group_dev_release_ship'):
            raise AccessError(_('You need the "Releases: Ship" permission to do this.'))

    def action_merge_branches(self):
        """Merge every branch of the release into its release branch on GitHub."""
        self._check_ship()
        self.ensure_one()
        repo = self.repository_id
        cancelled = repo._github_guard(_('Merge Branches'))
        if cancelled:
            return cancelled
        if not self.version:
            raise UserError(_('Give the release a release number first.'))
        created = repo._github_create_branch(self.release_branch)
        lines = []
        for branch in self.branch_ids:
            status, data = repo._github_request('POST', '/merges', {
                'base': self.release_branch,
                'head': branch.name,
                'commit_message': _('Merge %(branch)s into %(release)s', branch=branch.name,
                                    release=self.release_branch),
            }, ok_statuses=(404, 409, 422))
            if status == 201:
                merge_state, detail = 'merged', (data.get('sha') or '')[:12]
            elif status == 204:
                merge_state, detail = 'up_to_date', _('Already merged')
            elif status == 409:
                merge_state, detail = 'conflict', _('Merge conflict: resolve it on GitHub')
            elif status == 404:
                merge_state, detail = 'missing', _('Branch not found on GitHub')
            else:
                merge_state, detail = 'failed', (data.get('message') if isinstance(data, dict) else '') or str(status)
            branch.sudo().write({'merge_state': merge_state, 'merge_message': detail,
                                 'merged_release_id': self.id})
            lines.append(Markup('<li><strong>%s</strong>: %s (%s)</li>') % (
                branch.name, dict(branch._fields['merge_state'].selection)[merge_state], detail))
        self.sudo().write({'release_branch_created': True})
        if self.github_release_id and not self.github_published:
            self._github_update_release(raise_errors=False)
        intro = (_('Created %s and merged the release\'s branches into it:', self.release_branch) if created
                 else _('Merged the release\'s branches into %s:', self.release_branch))
        self.message_post(body=Markup('<p>%s</p><ul>%s</ul>') % (intro, Markup('').join(lines))
                          if lines else _('%s is ready; this release has no branches to merge yet.',
                                          self.release_branch))
        problems = self.branch_ids.filtered(lambda b: b.merge_state in ('conflict', 'missing', 'failed'))
        if problems:
            return repo._notify(_('%(count)s branch(es) could not be merged: %(names)s. See the Branches tab.',
                                  count=len(problems), names=', '.join(problems.mapped('name'))), kind='warning')
        return repo._notify(_('All branches are merged into %s.', self.release_branch))

    def action_github_publish(self):
        """Publish the draft GitHub release, tagging the release number."""
        self._check_ship()
        cancelled = self.repository_id._github_guard(_('Publish on GitHub'))
        if cancelled:
            return cancelled
        for release in self:
            if not release.github_release_id:
                release._github_create_draft()
            release.repository_id._github('PATCH', '/releases/%s' % release.github_release_id,
                                          dict(release._github_payload(draft=False), make_latest='true'))
            release.sudo().write({'github_published': True, 'github_error': False})
            release.message_post(body=_('Published %s on GitHub.', release.version))
        return True

    # ── AI ─────────────────────────────────────────────────────────────────
    @api.model
    def _name_prompt(self):
        return (self.env['ir.config_parameter'].sudo().get_param(PARAM_PROMPT) or '').strip()

    @api.model
    def _trigger_ai_naming(self):
        cron = self.env.ref('dev_management.ir_cron_dev_release_ai_name', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_ai_name(self):
        """Name the releases created while a naming prompt is set (background, after creation)."""
        if not self.env['dev.ai']._available() or not self._name_prompt():
            return
        releases = self.search([('ai_name_state', '=', 'pending')], order='id')
        Cron = self.env['ir.cron']
        # Commit after each release when run as the scheduled job (not when called directly).
        in_cron = bool(self.env.context.get('ir_cron_progress_id'))
        if in_cron:
            Cron._commit_progress(remaining=len(releases))
        for release in releases:
            try:
                with self.env.cr.savepoint():
                    release._ai_release_name()
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the others
                _logger.warning('AI naming of release %s failed: %s', release.id, exc)
                release.write({'ai_name_state': 'failed', 'ai_name_error': str(exc)[:500]})
            if in_cron and not Cron._commit_progress(1):
                break

    def _ai_release_name_info(self):
        prompt = self._name_prompt()
        return {
            'title': _('Naming the release with AI'),
            'step': _('Asking %(provider)s for a release name on the theme "%(theme)s", with trivia about it',
                      provider=self.env['dev.ai']._provider_label(), theme=prompt or _('(no prompt set)')),
        }

    def _ai_release_name(self):
        self.ensure_one()
        prompt = self._name_prompt()
        if not prompt:
            raise UserError(_('Set the release naming prompt in Development > Configuration > Settings first.'))
        used = self.with_context(active_test=False).search([('id', '!=', self.id)], limit=300).mapped('name')
        data = self._ai_json(
            _('Name a software release. Naming theme / instructions: %(prompt)s\n\n'
              'Names already used (never reuse one): %(used)s\n\n'
              'Pick one new name that fits the theme, then write trivia about it: 4 to 8 short lines of key '
              'facts (what or who it is, why it is notable, key dates and a fun fact), each line on its own, '
              'in plain text with no markdown.\n\n'
              'Answer with JSON only: {"name": "...", "trivia": "..."}',
              prompt=prompt, used=', '.join(n for n in used if n) or _('none')),
            system=_('You name software releases after real things or people, and know reliable facts about them.'),
            max_tokens=1500)
        name = (data.get('name') or '').strip()
        if not name:
            raise UserError(_('The AI did not suggest a name. Please try again.'))
        self.write({'name': name[:120], 'trivia': (data.get('trivia') or '').strip(), 'ai_name_state': 'done',
                    'ai_name_error': False})
        return _('The release is now called %s.', name)

    def _ai_release_notes_info(self):
        return {
            'title': _('Writing release notes with AI'),
            'step': _('Asking %(provider)s to write release notes from %(tickets)s ticket(s) and %(features)s '
                      'feature(s)', provider=self.env['dev.ai']._provider_label(),
                      tickets=len(self.ticket_ids), features=len(self.feature_ids)),
        }

    def _ai_release_notes(self):
        self.ensure_one()
        if not self.ticket_ids and not self.feature_ids:
            raise UserError(_('Add tickets or features to the release first.'))
        items = ['FEATURE %s: %s\n%s' % (f.key, f.name, html2plaintext(f.description or '')[:800])
                 for f in self.feature_ids]
        items += ['%s %s (%s, %s): %s\n%s' % ((t.type_id.name or 'Ticket').upper(), t.key, t.stage_id.name or '',
                                             t.priority_id.name or '', t.name,
                                             html2plaintext(t.description or '')[:500])
                  for t in self.ticket_ids]
        data = self._ai_json(
            _('Write release notes for release %(version)s "%(name)s" of %(repo)s, for its users.\n'
              'Group the changes under headings (New Features, Improvements, Bug Fixes, ...), explain each in '
              'one plain sentence of user benefit, and start with a two-sentence summary. Leave out internal '
              'jargon and ticket numbers.\n\nChanges:\n%(items)s\n\n'
              'Answer with JSON only: {"html": "<p>...</p><h3>...</h3><ul><li>...</li></ul>"} using only the '
              'tags p, h3, ul, li, strong and em.',
              version=self.version, name=self.name, repo=self.repository_id.name, items='\n\n'.join(items)[:60000]),
            system=_('You are a technical writer who writes clear, friendly release notes.'),
            max_tokens=4000)
        html = data.get('html')
        if not html:
            raise UserError(_('The AI did not return release notes. Please try again.'))
        self.release_notes = html
        return _('The release notes have been written. See the Release Notes tab.')

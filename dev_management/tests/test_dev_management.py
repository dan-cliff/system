from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, freeze_time, new_test_user, tagged

from odoo.addons.dev_management.models.dev_release import first_monday


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.content = b'x' if data is not None else b''
        self.text = str(data)

    def json(self):
        return self._data


class FakeGithub:
    """Answers the GitHub REST calls the app makes, recording them."""

    def __init__(self, tags=(), releases=()):
        self.tags = list(tags)
        self.releases = list(releases)
        self.calls = []
        self.branches = {'main': 'sha-main'}

    def __call__(self, method, url, json=None, params=None, timeout=None, headers=None):
        path = url.split('/repos/acme/app', 1)[1]
        self.calls.append((method, path, json))
        page = (params or {}).get('page', 1)
        if method == 'GET' and path == '/tags':
            return FakeResponse(200, [{'name': t} for t in self.tags] if page == 1 else [])
        if method == 'GET' and path == '/releases':
            return FakeResponse(200, [{'tag_name': t} for t in self.releases] if page == 1 else [])
        if method == 'POST' and path == '/releases':
            return FakeResponse(201, {'id': 77, 'html_url': 'https://github.com/acme/app/releases/77'})
        if method == 'PATCH' and path.startswith('/releases/'):
            return FakeResponse(200, {'id': 77})
        if method == 'GET' and path.startswith('/git/ref/heads/'):
            name = path[len('/git/ref/heads/'):]
            if name in self.branches:
                return FakeResponse(200, {'object': {'sha': self.branches[name]}})
            return FakeResponse(404, {'message': 'Not Found'})
        if method == 'POST' and path == '/git/refs':
            self.branches[json['ref'][len('refs/heads/'):]] = json['sha']
            return FakeResponse(201, {})
        if method == 'POST' and path == '/merges':
            if json['head'] == 'feature/conflict':
                return FakeResponse(409, {'message': 'Merge conflict'})
            return FakeResponse(201, {'sha': 'abc123def4567890'})
        return FakeResponse(404, {'message': 'Not Found'})


@tagged('post_install', '-at_install')
class TestDevManagement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.repo = cls.env['dev.repository'].create({'name': 'App', 'full_name': 'acme/app'})
        cls.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.api_key', '')
        cls.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.gemini_api_key', '')

    def _release(self, **vals):
        return self.env['dev.release'].create(dict({'repository_id': self.repo.id}, **vals))

    # ── Dates ──────────────────────────────────────────────────────────────
    def test_first_monday(self):
        self.assertEqual(first_monday(date(2026, 10, 26)), date(2026, 10, 26))  # Monday
        self.assertEqual(first_monday(date(2026, 10, 27)), date(2026, 11, 2))  # Tuesday
        self.assertEqual(first_monday(date(2026, 11, 1)), date(2026, 11, 2))  # Sunday

    @freeze_time('2026-10-27')
    def test_release_dates(self):
        release = self._release()
        self.assertEqual(release.date_start, date(2026, 11, 2))
        self.assertEqual(release.date_end, date(2026, 11, 15))  # Sunday, two weeks on
        self.assertEqual(release.date_end.weekday(), 6)
        self.assertEqual(release.date_alpha, date(2026, 11, 29))
        self.assertEqual(release.date_beta, date(2026, 12, 6))
        self.assertEqual(release.date_core, date(2026, 12, 20))
        self.assertFalse(release.date_closed)
        # Dates stay editable, and the later ones follow an edited one.
        release.date_alpha = date(2026, 12, 1)
        self.assertEqual(release.date_beta, date(2026, 12, 8))

    # ── Release numbers ────────────────────────────────────────────────────
    @freeze_time('2026-10-27')
    def test_version_local(self):
        first = self._release()
        second = self._release()
        self.assertEqual(first.version, '2026.10.001')
        self.assertEqual(second.version, '2026.10.002')
        manual = self._release(version='2026.10.009')
        self.assertEqual(manual.version, '2026.10.009')
        self.assertEqual(self._release().version, '2026.10.010')

    @freeze_time('2026-10-27')
    def test_version_from_github_and_draft_release(self):
        self.repo.github_token = 'token'
        fake = FakeGithub(tags=['2026.10.002', '2026.09.007', 'v1.0'], releases=['2026.10.004'])
        with patch('odoo.addons.dev_management.models.dev_repository.requests.request', fake):
            release = self._release()
        self.assertEqual(release.version, '2026.10.005')
        self.assertEqual(release.github_release_id, 77)
        post = [c for c in fake.calls if c[0] == 'POST' and c[1] == '/releases'][0][2]
        self.assertTrue(post['draft'])
        self.assertEqual(post['tag_name'], '2026.10.005')
        self.assertEqual(post['target_commitish'], 'main')

    def test_github_failure_does_not_block_creation(self):
        self.repo.github_token = 'token'

        def boom(*args, **kwargs):
            raise __import__('requests').ConnectionError('offline')

        with patch('odoo.addons.dev_management.models.dev_repository.requests.request', boom):
            release = self._release()
        self.assertTrue(release.version)
        self.assertIn('could not be reached', release.github_error)

    # ── Workflow ───────────────────────────────────────────────────────────
    @freeze_time('2026-10-27')
    def test_workflow_next_release_and_closed_date(self):
        release = self._release()
        release.action_advance()
        self.assertEqual(release.state, 'open')
        release.action_advance()
        self.assertEqual(release.state, 'documentation')
        self.assertTrue(release.release_notes, 'Release notes are built when documentation starts')
        release.action_advance()
        self.assertEqual(release.state, 'review')
        following = release.next_release_id
        self.assertTrue(following, 'Reaching Review creates the next release')
        self.assertEqual(following.repository_id, self.repo)
        self.assertEqual(following.previous_release_id, release)
        self.assertEqual(following.date_start, date(2026, 11, 16), 'Starts the Monday after the End Date')
        self.assertEqual(following.version, '2026.10.002')
        # Going back to Review doesn't create another one.
        release.action_back()
        release.action_advance()
        self.assertEqual(self.env['dev.release'].search_count([('previous_release_id', '=', release.id)]), 1)
        for state in ('complete', 'alpha', 'beta', 'core', 'closed'):
            release.action_advance()
            self.assertEqual(release.state, state)
        self.assertEqual(release.date_closed, date(2026, 10, 27))
        release.action_back()
        self.assertFalse(release.date_closed)

    def test_ship_permission(self):
        user = new_test_user(self.env, 'dev_editor', groups='base.group_user,dev_management.group_dev_release_edit_all')
        release = self._release(state='complete')
        with self.assertRaises(AccessError):
            release.with_user(user).action_advance()
        user.group_ids += self.env.ref('dev_management.group_dev_release_ship')
        release.with_user(user).action_advance()
        self.assertEqual(release.state, 'alpha')

    def test_move_open_tickets(self):
        release = self._release()
        done_stage = self.env.ref('dev_management.ticket_stage_done')
        done = self.env['dev.ticket'].create({'name': 'Done', 'release_id': release.id, 'stage_id': done_stage.id})
        todo = self.env['dev.ticket'].create({'name': 'To do', 'release_id': release.id})
        release.action_move_open_tickets()
        self.assertEqual(done.release_id, release)
        self.assertEqual(todo.release_id, release.next_release_id)

    def test_merge_branches(self):
        self.repo.github_token = 'token'
        fake = FakeGithub()
        with patch('odoo.addons.dev_management.models.dev_repository.requests.request', fake):
            release = self._release()
            good = self.env['dev.branch'].create({'name': 'feature/good', 'repository_id': self.repo.id})
            bad = self.env['dev.branch'].create({'name': 'feature/conflict', 'repository_id': self.repo.id})
            self.env['dev.ticket'].create({'name': 'A', 'release_id': release.id, 'branch_ids': [(6, 0, good.ids)]})
            self.env['dev.ticket'].create({'name': 'B', 'release_id': release.id, 'branch_ids': [(6, 0, bad.ids)]})
            self.assertEqual(release.branch_ids, good | bad)
            release.action_merge_branches()
        self.assertIn('release/%s' % release.version, fake.branches)
        self.assertEqual(good.merge_state, 'merged')
        self.assertEqual(bad.merge_state, 'conflict')
        self.assertTrue(release.release_branch_created)

    # ── Tickets ────────────────────────────────────────────────────────────
    def test_ticket_keys_links_and_branch_names(self):
        Ticket = self.env['dev.ticket']
        blocker = Ticket.create({'name': 'Build the API'})
        blocked = Ticket.create({'name': 'Build the screen'})
        self.assertTrue(blocker.key.startswith('DEV-'))
        self.env['dev.ticket.link'].create({
            'source_id': blocker.id, 'target_id': blocked.id,
            'link_type_id': self.env.ref('dev_management.link_type_blocks').id})
        self.assertTrue(blocked.is_blocked)
        self.assertIn(blocked, Ticket.search([('is_blocked', '=', True)]))
        blocker.stage_id = self.env.ref('dev_management.ticket_stage_done')
        self.assertFalse(blocked.is_blocked)
        self.assertTrue(blocker.date_closed)
        bug = Ticket.create({'name': 'Login fails: "500"!', 'type_id': self.env.ref('dev_management.ticket_type_bug').id})
        self.assertEqual(bug._branch_name(), 'bugfix/%s-login-fails-500' % bug.key)

    # ── Documentation ──────────────────────────────────────────────────────
    def test_page_history(self):
        space = self.env['dev.space'].create({'name': 'Handbook'})
        template = self.env.ref('dev_management.page_template_meeting')
        page = self.env['dev.page'].create({'name': 'Kick-off', 'space_id': space.id, 'template_id': template.id})
        self.assertIn('Attendees', page.body)
        child = self.env['dev.page'].create({'name': 'Child', 'parent_id': page.id})
        self.assertEqual(child.space_id, space)
        page.body = '<p>Second</p>'
        self.assertEqual(page.version_count, 1)
        page.version_ids.action_restore()
        self.assertIn('Attendees', page.body)

    # ── AI ─────────────────────────────────────────────────────────────────
    def test_ai_gated_without_keys(self):
        self.env['ir.config_parameter'].sudo().set_param('dev_management.release_name_prompt', 'Planets')
        release = self._release()
        self.assertFalse(release.ai_available)
        self.assertFalse(release.ai_name_state, 'No AI key: nothing is queued')
        self.assertEqual(release.name, release.version)
        with self.assertRaises(UserError):
            release.action_ai_run('release_name')
        # The background job does nothing without a key.
        self.env['dev.release']._cron_ai_name()

    def test_ai_release_name(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('dev_management.release_name_prompt', 'Planets')
        params.set_param('ai.anthropic_key', 'sk-test')
        release = self._release()
        self.assertTrue(release.ai_available)
        self.assertEqual(release.ai_name_state, 'pending')
        answer = {'name': 'Jupiter', 'trivia': 'The largest planet.'}
        with patch('odoo.addons.dev_management.models.dev_ai.ai_request_json', return_value=answer) as request:
            self.env['dev.release']._cron_ai_name()
        self.assertTrue(request.called)
        self.assertEqual(release.name, 'Jupiter')
        self.assertEqual(release.trivia, 'The largest planet.')
        self.assertEqual(release.ai_name_state, 'done')
        self.assertEqual(release.display_name, '%s Jupiter' % release.version)
        info = release.get_ai_job_info('release_name')
        self.assertIn('Planets', info['step'])
        self.assertIn('Claude', info['step'])

    def test_record_rules(self):
        """Create and Edit Own: their own tickets only; children follow their ticket."""
        own = new_test_user(self.env, 'dev_own', groups='base.group_user,dev_management.group_dev_ticket_edit_own')
        theirs = self.env['dev.ticket'].create({'name': 'Someone else\'s', 'criterion_ids': [(0, 0, {'name': 'X'})]})
        Ticket = self.env['dev.ticket'].with_user(own)
        mine = Ticket.create({'name': 'Mine', 'criterion_ids': [(0, 0, {'name': 'Works'})]})
        mine.name = 'Mine, edited'
        self.assertEqual(Ticket.search([]), mine)
        self.assertEqual(self.env['dev.acceptance.criterion'].with_user(own).search([]), mine.criterion_ids)
        with self.assertRaises(AccessError):
            theirs.with_user(own).name
        with self.assertRaises(AccessError):
            mine.unlink()
        # Assigned to them counts as their own.
        theirs.user_id = own
        self.assertEqual(Ticket.search([]), mine | theirs)
        # Without any permission, nothing.
        nobody = new_test_user(self.env, 'dev_nobody', groups='base.group_user,dev_management.group_dev_user')
        self.assertFalse(self.env['dev.ticket'].with_user(nobody).search([]))

    def test_github_cancelled_without_token(self):
        """Every GitHub request is cancelled gracefully when the repository has no access token."""
        def no_call(*args, **kwargs):
            raise AssertionError('GitHub must not be called without a token')

        with patch('odoo.addons.dev_management.models.dev_repository.requests.request', no_call):
            # Automatic requests are skipped: the release is still created and numbered.
            release = self._release(state='core')
            self.assertEqual(release.version[-3:], '001')
            self.assertFalse(release.github_release_id)
            self.assertFalse(release.github_error)
            release.name = 'Renamed'
            self.assertFalse(release.github_error)
            branch = self.env['dev.branch'].create({'name': 'feature/x', 'repository_id': self.repo.id})
            ticket = self.env['dev.ticket'].create({'name': 'T', 'release_id': release.id,
                                                    'branch_ids': [(6, 0, branch.ids)]})
            self.assertFalse(ticket.repository_token_set)
            # Requests made from buttons return a warning and change nothing.
            for action in (self.repo.action_test_connection, self.repo.action_sync_branches,
                           branch.action_sync, branch.action_create_on_github,
                           ticket.action_create_branch, release.action_github_create_release,
                           release.action_github_update_release, release.action_merge_branches,
                           release.action_github_publish):
                result = action()
                self.assertEqual(result['tag'], 'display_notification', action)
                self.assertEqual(result['params']['type'], 'warning')
                self.assertIn('cancelled', result['params']['message'])
            self.assertEqual(ticket.branch_ids, branch)
            self.assertFalse(branch.merge_state)
            self.assertFalse(release.release_branch_created)
            self.assertFalse(release.github_published)
            # A ticket without a repository is cancelled too.
            orphan = self.env['dev.ticket'].create({'name': 'No repository'})
            self.assertIn('choose a repository', orphan.action_create_branch()['params']['message'])
        # The low-level call still refuses (safety net) with a friendly error.
        with self.assertRaises(UserError):
            self.repo._github('GET', '')

from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, freeze_time, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDevSprint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.done = cls.env.ref('dev_management.ticket_stage_done')
        Ticket = cls.env['dev.ticket']
        cls.t1 = Ticket.create({'name': 'Login', 'story_points': 3})
        cls.t2 = Ticket.create({'name': 'Reset password', 'story_points': 5})
        cls.t3 = Ticket.create({'name': 'Audit log', 'story_points': 8})

    @freeze_time('2026-10-27')
    def test_sprint_lifecycle_and_carry_over(self):
        sprint = self.env['dev.sprint'].create({'ticket_ids': [(6, 0, (self.t1 | self.t2).ids)]})
        self.assertRegex(sprint.name, r'^Sprint 2026-\d{3}$')
        self.assertEqual(sprint.date_start, date(2026, 11, 2), 'Starts the first Monday')
        self.assertEqual(sprint.date_end, date(2026, 11, 15), 'Sprint length from Settings')
        self.assertEqual(self.t1.sprint_id, sprint)

        sprint.action_start()
        self.assertEqual(sprint.state, 'active')
        self.assertEqual(sprint.committed_points, 8)
        self.assertEqual(sprint.committed_ticket_ids, self.t1 | self.t2)
        # Scope added after the start shows in the sprint report.
        sprint.ticket_ids = [(4, self.t3.id)]
        self.assertEqual(sprint.added_ticket_ids, self.t3)

        self.t1.stage_id = self.done
        action = sprint.action_complete()
        self.assertEqual(action['res_model'], 'dev.sprint.complete', 'Unfinished tickets: ask where they go')
        wizard = Form(self.env['dev.sprint.complete'].with_context(action['context'])).save()
        self.assertEqual((wizard.done_count, wizard.open_count), (1, 2))
        self.assertTrue(wizard.create_next, 'No planned sprint yet: offer to create the next one')
        result = wizard.action_complete()
        following = self.env['dev.sprint'].browse(result['res_id'])

        self.assertEqual(sprint.state, 'closed')
        self.assertEqual(sprint.completed_points, 3, 'Velocity')
        self.assertEqual(sprint.completed_ticket_ids, self.t1)
        self.assertEqual(sprint.carried_over_ticket_ids, self.t2 | self.t3)
        self.assertEqual(sprint.next_sprint_id, following)
        self.assertEqual(following.date_start, date(2026, 11, 16), 'The day after the sprint ended')
        # Unfinished tickets are tracked across sprints: in both, current = the new one.
        self.assertEqual(self.t2.sprint_ids, sprint | following)
        self.assertEqual(self.t2.sprint_id, following)
        self.assertEqual(self.t2.sprint_count, 2)
        self.assertEqual(self.t1.sprint_ids, sprint, 'Done tickets stay in their sprint only')
        Ticket = self.env['dev.ticket']
        self.assertIn(self.t2, Ticket.search([('sprint_count', '>', 1)]), 'Carried Over filter')

    def test_complete_to_backlog_and_existing_sprint(self):
        Sprint = self.env['dev.sprint']
        first = Sprint.create({'date_start': date(2026, 11, 2), 'ticket_ids': [(6, 0, (self.t1 | self.t2).ids)]})
        second = Sprint.create({'date_start': date(2026, 11, 16)})
        first.action_start()
        wizard = Form(self.env['dev.sprint.complete'].with_context(default_sprint_id=first.id)).save()
        self.assertEqual(wizard.target_sprint_id, second, 'The next planned sprint is suggested')
        wizard.action_complete()
        self.assertIn(second, self.t1.sprint_ids)

        backlog_domain = [('sprint_ids', 'not any', [('state', 'in', ('planned', 'active'))])]
        third = Sprint.create({'ticket_ids': [(6, 0, self.t3.ids)]})
        third.action_start()
        self.assertNotIn(self.t3, self.env['dev.ticket'].search(backlog_domain))
        self.env['dev.sprint.complete'].create({'sprint_id': third.id}).action_complete()
        self.assertIn(self.t3, self.env['dev.ticket'].search(backlog_domain), 'Back to the backlog')
        self.assertEqual(self.t3.sprint_id, third, 'Its last sprint stays its current one until replanned')

    def test_start_checks(self):
        sprint = self.env['dev.sprint'].create({})
        with self.assertRaises(UserError):
            sprint.action_start()
        sprint.ticket_ids = self.t1
        sprint.action_start()
        with self.assertRaises(UserError):
            sprint.action_start()
        # All done: completes straight away, no question asked.
        self.t1.stage_id = self.done
        self.assertTrue(sprint.action_complete())
        self.assertEqual(sprint.state, 'closed')

    def test_epic_tracks_tickets_and_sprints(self):
        epic = self.env['dev.epic'].create({'name': 'Accounts'})
        self.assertTrue(epic.key.startswith('EPIC-'))
        self.assertEqual(epic.stage_id, self.env.ref('dev_management.epic_stage_todo'))
        (self.t1 | self.t2).epic_id = epic
        sprint_a = self.env['dev.sprint'].create({'ticket_ids': [(6, 0, self.t1.ids)]})
        sprint_b = self.env['dev.sprint'].create({})
        self.t2.sprint_ids = [(4, sprint_b.id)]
        self.assertEqual(epic.sprint_ids, sprint_a | sprint_b, 'The sprints of its tickets are tracked')
        self.t1.stage_id = self.done
        self.assertEqual((epic.ticket_count, epic.ticket_done_count), (2, 1))
        self.assertAlmostEqual(epic.progress, 100.0 * 3 / 8)
        # A ticket created in a feature of the epic picks the epic up.
        feature = self.env['dev.feature'].create({'name': 'SSO', 'epic_id': epic.id})
        with Form(self.env['dev.ticket']) as form:
            form.name = 'SAML'
            form.feature_id = feature
        self.assertEqual(form.record.epic_id, epic)

    def test_add_to_sprint_wizard(self):
        sprint = self.env['dev.sprint'].create({})
        tickets = self.t1 | self.t3
        wizard = self.env['dev.ticket.add.sprint'].with_context(active_ids=tickets.ids).create({'sprint_id': sprint.id})
        wizard.action_add()
        self.assertEqual(sprint.ticket_ids, tickets)

    @freeze_time('2026-11-06 12:00:00')
    def test_burndown(self):
        sprint = self.env['dev.sprint'].create({
            'date_start': date(2026, 11, 2), 'date_end': date(2026, 11, 13),
            'ticket_ids': [(6, 0, (self.t1 | self.t2 | self.t3).ids)]})
        sprint.action_start()
        self.t1.write({'stage_id': self.done.id})
        self.t1.date_closed = datetime(2026, 11, 4, 9, 0)
        days, ideal, actual = sprint._burndown_series()
        self.assertEqual(len(days), 12)
        self.assertEqual(ideal[0], 16)
        self.assertEqual(ideal[-1], 0)
        self.assertEqual(actual, [16, 16, 13, 13, 13], 'Up to today: 3 points done on the 4th')
        self.assertIn('<svg', sprint.burndown)

    def test_sprint_permissions(self):
        """Sprints follow the CLAUDE.md permission model: own sprints with Create and Edit Own."""
        user = new_test_user(self.env, 'sprint_own', groups='base.group_user,dev_management.group_dev_sprint_edit_own')
        mine = self.env['dev.sprint'].with_user(user).create({'name': 'Mine'})
        theirs = self.env['dev.sprint'].create({'name': 'Theirs'})
        self.assertEqual(self.env['dev.sprint'].with_user(user).search([('id', 'in', (mine | theirs).ids)]), mine)
        theirs.user_id = user
        self.assertEqual(self.env['dev.sprint'].with_user(user).search([('id', 'in', (mine | theirs).ids)]),
                         mine | theirs, 'The Scrum Master counts as owner')

    def test_sprint_names(self):
        """Sprint YYYY-NNN: numbered within the year the sprint starts in."""
        import re
        Sprint = self.env['dev.sprint']
        first = Sprint.create({'date_start': date(2026, 11, 2)})
        second = Sprint.create({'date_start': date(2026, 11, 16)})
        next_year = Sprint.create({'date_start': date(2027, 1, 4)})
        for sprint, year in ((first, 2026), (second, 2026), (next_year, 2027)):
            self.assertRegex(sprint.name, r'^Sprint %s-\d{3}$' % year)
        number = lambda s: int(re.search(r'-(\d+)$', s.name).group(1))  # noqa: E731
        self.assertEqual(number(second), number(first) + 1)
        self.assertEqual(Sprint.create({'name': 'Hardening', 'date_start': date(2026, 12, 1)}).name, 'Hardening',
                         'A name typed in is kept')
        # The next sprint created on completion is named for its own start year.
        late = Sprint.create({'date_start': date(2026, 12, 14), 'date_end': date(2026, 12, 27)})
        self.assertRegex(late._create_next_sprint().name, r'^Sprint 2026-\d{3}$')
        self.assertRegex(Sprint.create({'date_start': date(2026, 12, 28),
                                        'date_end': date(2027, 1, 10)})._create_next_sprint().name,
                         r'^Sprint 2027-\d{3}$')

    def test_bulk_update(self):
        Sprint = self.env['dev.sprint']
        old = Sprint.create({'date_start': date(2026, 11, 2), 'ticket_ids': [(6, 0, (self.t1 | self.t2).ids)]})
        past = Sprint.create({'date_start': date(2026, 10, 5), 'ticket_ids': [(6, 0, self.t1.ids)]})
        past.state = 'closed'
        new = Sprint.create({'date_start': date(2026, 11, 16)})
        epic = self.env['dev.epic'].create({'name': 'Accounts'})
        repo = self.env['dev.repository'].create({'name': 'App', 'full_name': 'acme/bulk'})
        release = self.env['dev.release'].create({'name': 'R1', 'repository_id': repo.id})
        bug = self.env['dev.ticket.type'].create({'name': 'Bulk Bug'})
        tag_a, tag_b = self.env['dev.tag'].create([{'name': 'bulk-a'}, {'name': 'bulk-b'}])
        user = new_test_user(self.env, 'bulk_assignee', groups='base.group_user')
        self.t1.tag_ids = tag_a
        self.t2.user_id = user
        tickets = self.t1 | self.t2
        Wizard = self.env['dev.ticket.bulk.update'].with_context(active_ids=tickets.ids)

        Wizard.create({
            'update_epic': True, 'epic_id': epic.id,
            'update_user': True, 'user_id': user.id,
            'update_type': True, 'type_id': bug.id,
            'update_release': True, 'release_id': release.id,
            'update_story_points': True, 'story_points': 2,
            'update_date_deadline': True, 'date_deadline': date(2026, 12, 1),
            'update_company': True, 'company_id': self.env.company.id,
            'tag_mode': 'add', 'tag_ids': [(6, 0, tag_b.ids)],
            'sprint_mode': 'replace', 'sprint_ids': [(6, 0, new.ids)],
        }).action_apply()
        for ticket in tickets:
            self.assertEqual((ticket.epic_id, ticket.user_id, ticket.type_id, ticket.release_id),
                             (epic, user, bug, release))
            self.assertEqual((ticket.story_points, ticket.date_deadline), (2, date(2026, 12, 1)))
        self.assertEqual(self.t1.tag_ids, tag_a | tag_b)
        self.assertEqual(self.t2.tag_ids, tag_b)
        self.assertEqual(self.t1.sprint_ids, past | new, 'Open sprints replaced, completed ones kept as history')
        self.assertEqual(self.t2.sprint_ids, new)
        self.assertIn(new, epic.sprint_ids, 'The epic tracks the new sprint')

        # Unticked fields are left alone; a ticked empty one is cleared.
        Wizard.create({'epic_id': False, 'update_user': True, 'tag_mode': 'remove',
                       'tag_ids': [(6, 0, tag_a.ids)], 'sprint_mode': 'add',
                       'sprint_ids': [(6, 0, old.ids)]}).action_apply()
        self.assertEqual(self.t1.epic_id, epic)
        self.assertFalse(tickets.user_id)
        self.assertEqual(self.t1.tag_ids, tag_b)
        self.assertEqual(self.t2.sprint_ids, old | new)

        Wizard.create({'sprint_mode': 'replace', 'sprint_from_ids': [(6, 0, old.ids)]}).action_apply()
        self.assertEqual(self.t2.sprint_ids, new, 'Only the named sprint is replaced (here with none)')
        Wizard.create({'sprint_mode': 'remove', 'sprint_ids': [(6, 0, new.ids)],
                       'tag_mode': 'replace'}).action_apply()
        self.assertFalse(self.t2.sprint_ids)
        self.assertFalse(tickets.tag_ids)
        with self.assertRaises(UserError):
            Wizard.create({'update_company': True}).action_apply()

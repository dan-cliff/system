from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import AdvancedProjectCommon


@tagged('post_install', '-at_install')
class TestAdvancedProjectFlow(AdvancedProjectCommon):
    """Plans, templates, the Overview, Project Updates and the Gantt view."""

    def test_new_project_gets_overview_and_manager_on_team(self):
        project = self._project(self.admin)
        self.assertTrue(project.overview_widget_ids)
        self.assertEqual(project.collaborator_ids.partner_id, self.admin.partner_id)
        self.assertEqual(project.collaborator_ids.collaborator_type, 'colleague')

    def test_assignees_join_the_team(self):
        project = self._project(self.admin)
        other = self._user('ap_assignee', 'edit_own')
        self._task(project, user_ids=[(6, 0, other.ids)])
        self.assertIn(other.partner_id, project.collaborator_ids.partner_id)

    def test_task_links_and_completion(self):
        project = self._project()
        a, b, c = (self._task(project, name=name) for name in 'ABC')
        a.child_ids = [(6, 0, (b | c).ids)]
        self.assertEqual(c.parent_ids, a)
        b.child_ids = [(4, c.id)]
        self.assertEqual(c.parent_ids, a | b)  # many2many: several parents
        with self.assertRaises(ValidationError):
            c.child_ids = [(4, a.id)]  # no loops
        other_project = self._project(name='Other')
        with self.assertRaises(ValidationError):
            a.child_ids = [(4, self._task(other_project).id)]
        self.assertFalse(a.date_done)
        a.stage_id = self.stage_done
        self.assertTrue(a.date_done)
        a.stage_id = self.stage_todo
        self.assertFalse(a.date_done)
        with self.assertRaises(ValidationError):
            a.write({'date_start': date(2026, 3, 10), 'date_end': date(2026, 3, 1)})

    def test_progress_and_overdue(self):
        project = self._project()
        yesterday = fields.Date.today() - timedelta(days=1)
        late = self._task(project, date_end=yesterday)
        self._task(project, stage_id=self.stage_done.id, date_end=yesterday)
        self._task(project, stage_id=self.env.ref('advanced_projects.task_stage_cancelled').id)
        self.assertEqual(project.progress, 50.0)
        Task = self.env['advanced.project.task']
        self.assertEqual(Task.search([('project_id', '=', project.id), ('is_overdue', '=', True)]), late)

    def test_create_from_template_shifts_dates_and_copies_links(self):
        template = self.env.ref('advanced_projects.template_customer_onboarding')
        start = date(2026, 6, 1)
        wizard = self.env['advanced.project.from.template'].with_user(self.admin).create({
            'template_id': template.id, 'partner_id': self.customer_company.id, 'date_start': start,
        })
        self.assertEqual(wizard.name, 'Customer Onboarding – Acme Farms')
        action = wizard.action_create()
        project = self.env['advanced.project'].browse(action['res_id'])
        self.assertFalse(project.is_template)
        self.assertEqual(project.template_id, template)
        self.assertEqual(project.create_uid, self.admin)
        self.assertEqual(len(project.phase_ids), len(template.phase_ids))
        self.assertEqual(len(project.task_ids), len(template.task_ids))
        shift = (start - template.date_start).days
        kickoff = project.task_ids.filtered(lambda t: t.name == 'Kick-off meeting')
        template_kickoff = template.task_ids.filtered(lambda t: t.name == 'Kick-off meeting')
        self.assertEqual(kickoff.date_start, template_kickoff.date_start + timedelta(days=shift))
        self.assertEqual(kickoff.phase_id.project_id, project)
        signoff = project.task_ids.filtered(lambda t: t.name == 'Sign off requirements')
        self.assertEqual(signoff.parent_ids.mapped('name'), ['Requirements workshop', 'Collect customer data and documents'])
        self.assertTrue(signoff.parent_ids <= project.task_ids)
        self.assertEqual(len(project.overview_widget_ids), len(template.overview_widget_ids))
        self.assertTrue(all(t.stage_id == self.stage_todo for t in project.task_ids))

    def test_copy_project_copies_plan(self):
        project = self._project()
        phase = self.env['advanced.project.phase'].create({'name': 'Build', 'project_id': project.id})
        a = self._task(project, name='A', phase_id=phase.id)
        b = self._task(project, name='B', phase_id=phase.id, parent_ids=[(6, 0, a.ids)])
        copy = project.copy()
        self.assertEqual(copy.name, 'Website Launch (copy)')
        self.assertEqual(copy.task_ids.mapped('name'), ['A', 'B'])
        new_b = copy.task_ids.filtered(lambda t: t.name == 'B')
        self.assertEqual(new_b.parent_ids.name, 'A')
        self.assertNotEqual(new_b.parent_ids, a)
        self.assertEqual(new_b.phase_id.project_id, copy)
        self.assertTrue(b.parent_ids == a)

    def test_budget(self):
        project = self._project(self.admin)
        phase = self.env['advanced.project.phase'].create({'project_id': project.id, 'name': 'Build'})
        self._task(project, planned_hours=30)
        self._task(project, planned_hours=20)
        labour = self.env.ref('advanced_projects.budget_category_labour')
        materials = self.env.ref('advanced_projects.budget_category_materials')
        Line = self.env['advanced.project.budget.line'].with_user(self.admin)
        Line.create([
            {'project_id': project.id, 'category_id': labour.id, 'phase_id': phase.id,
             'allocated_hours': 40, 'amount': 2000, 'spent_amount': 500},
            {'project_id': project.id, 'category_id': materials.id, 'name': 'Timber',
             'amount': 1000, 'spent_amount': 1250},
        ])
        self.assertEqual(project.currency_id, self.env.company.currency_id)
        self.assertEqual(project.allocated_hours, 40)
        self.assertEqual(project.planned_hours, 50)
        self.assertEqual(project.budget_amount, 3000)
        self.assertEqual(project.spent_amount, 1750)
        self.assertEqual(project.remaining_budget, 1250)
        self.assertAlmostEqual(project.budget_used, 58.33, places=2)

        widget = self.env['advanced.project.overview.widget'].with_user(self.admin).browse(
            project.with_user(self.admin).overview_add_widget('budget'))
        data = widget._overview_values()['data']
        self.assertEqual(data['hours']['allocated'], '40:00')
        self.assertEqual(data['hours']['planned'], '50:00')
        self.assertTrue(data['hours']['over_planned'])
        self.assertEqual(data['money']['percent'], 58)
        self.assertFalse(data['money']['over'])
        self.assertEqual([line['name'] for line in data['lines']], ['Labour', 'Timber'])
        self.assertEqual(data['lines'][0]['detail'], 'Build')
        self.assertEqual(data['lines'][1]['detail'], 'Materials')
        self.assertTrue(data['lines'][1]['over'])

        # copies and projects made from it keep the budget, not what was spent
        copy = project.with_user(self.admin).copy()
        self.assertEqual(copy.budget_amount, 3000)
        self.assertEqual(copy.spent_amount, 0)
        self.assertEqual(copy.budget_line_ids[0].phase_id.project_id, copy)

    def test_overview_data(self):
        project = self._project(self.admin, date_end=fields.Date.today() + timedelta(days=30))
        project.overview_add_widget('workload')
        project.overview_add_widget('note')
        self._task(project, stage_id=self.stage_blocked.id, user_ids=[(6, 0, self.admin.ids)])
        data = project.with_user(self.admin).get_overview_data()
        self.assertTrue(data['can_edit'])
        types = {w['widget_type'] for w in data['widgets']}
        self.assertTrue({'progress', 'task_counts', 'phases', 'task_list', 'stage_chart', 'team',
                         'latest_update', 'workload', 'note'} <= types)
        blocked = next(w for w in data['widgets'] if w['widget_type'] == 'task_list'
                       and w['data']['task_filter'] == 'blocked')
        self.assertEqual(len(blocked['data']['rows']), 1)
        # new widgets go below the others; the grid layout is saved as dragged
        note = next(w for w in data['widgets'] if w['widget_type'] == 'note')
        self.assertEqual((note['x'], note['w'], note['h']), (0, 4, 3))
        self.assertGreaterEqual(note['y'], 17)
        progress = next(w for w in data['widgets'] if w['widget_type'] == 'progress')
        project.overview_save_layout([
            {'id': note['id'], 'x': 0, 'y': 0, 'w': 12, 'h': 2},
            {'id': progress['id'], 'x': 3, 'y': 2, 'w': 20, 'h': 0},
        ])
        self.assertEqual(project.overview_widget_ids[0].id, note['id'])
        moved = project.overview_widget_ids.filtered(lambda w: w.id == progress['id'])
        self.assertEqual((moved.grid_x, moved.grid_y, moved.grid_w, moved.grid_h), (3, 2, 12, 1))
        dropped = project.overview_add_widget('team', False, 8, 1, 4, 6)
        dropped = self.env['advanced.project.overview.widget'].browse(dropped)
        self.assertEqual((dropped.grid_x, dropped.grid_y, dropped.grid_w, dropped.grid_h), (8, 1, 4, 6))
        project.overview_reset()
        self.assertEqual(len(project.overview_widget_ids), 9)
        action = project.action_open_tasks_filtered('blocked')
        self.assertEqual(self.env['advanced.project.task'].search(action['domain']).stage_id, self.stage_blocked)

    def test_update_editor_and_publish(self):
        project = self._project(self.admin)
        phase = self.env['advanced.project.phase'].create({'name': 'Build', 'project_id': project.id})
        done = self._task(project, name='Done task', stage_id=self.stage_done.id, phase_id=phase.id)
        self._task(project, name='Blocked task', stage_id=self.stage_blocked.id)
        update = self.env['advanced.project.update'].with_user(self.admin).create({
            'project_id': project.id, 'status_id': self.env.ref('advanced_projects.project_status_at_risk').id,
        })
        self.assertEqual(update.block_ids.mapped('block_type'), ['text', 'tasks', 'tasks', 'tasks'])
        data = update.get_editor_data()
        completed = next(b for b in data['blocks'] if b.get('task_filter') == 'completed')
        self.assertEqual([r['id'] for r in completed['rows']], done.ids)
        # drag a widget in at the top, filtered on a phase
        block = update.editor_add_block('tasks', 'outstanding', 0)
        self.assertEqual(update.block_ids[0].id, block['id'])
        update.block_ids[0].write({'phase_ids': [(6, 0, phase.ids)]})
        self.assertEqual(update.block_ids[0]._filter_values()['rows'], [])
        update.block_ids.filtered(lambda b: b.block_type == 'text').body = '<p>All good</p>'
        update.editor_resequence(update.block_ids.ids[::-1])
        # blocks span 12 columns until resized; side by side when narrower
        self.assertEqual(set(update.block_ids.mapped('width')), {12})
        update.block_ids[0].width = 6
        self.assertEqual(update.get_editor_data()['blocks'][0]['width'], 6)
        with self.assertRaises(Exception), self.cr.savepoint():
            update.block_ids[1].width = 13
            update.block_ids[1].flush_recordset()

        publisher = self._user('ap_publisher', 'edit_own')
        with self.assertRaises(AccessError):
            update.with_user(publisher).action_publish()
        update.with_user(self.admin).action_publish()
        self.assertEqual(update.state, 'published')
        self.assertIn('Done task', update.body_html)
        self.assertIn('All good', update.body_html)
        self.assertEqual([len(row) for row in update._document_rows()], [1] * 5)
        self.assertIn('width:50.0%', update.body_html)
        self.assertIn('width:100.0%', update.body_html)
        self.assertEqual(project.status_id, update.status_id)
        posted = project.message_ids.filtered(lambda m: 'Project Update published' in (m.body or ''))
        self.assertTrue(posted)
        self.assertFalse(posted.is_internal)
        # frozen: the published list does not change, and blocks are locked
        done.stage_id = self.stage_todo
        self.assertIn('Done task', update.body_html)
        with self.assertRaises(UserError):
            update.block_ids[0].write({'title': 'Changed'})
        update.with_user(self.admin).action_reset_draft()
        self.assertEqual(update.state, 'draft')
        self.assertFalse(update.body_html)

    def test_internal_update_posts_a_private_message(self):
        project = self._project(self.admin)
        update = self.env['advanced.project.update'].create({'project_id': project.id, 'customer_visible': False})
        update.with_user(self.admin).action_publish()
        posted = project.message_ids.filtered(lambda m: 'Project Update published' in (m.body or ''))
        self.assertTrue(posted.is_internal)

    def test_gantt_view(self):
        views = self.env['advanced.project.task'].get_views([(False, 'project_gantt')])
        arch = views['views']['project_gantt']['arch']
        self.assertIn('date_start="date_start"', arch)
        with self.assertRaises(ValidationError):
            self.env['ir.ui.view'].create({
                'name': 'bad gantt', 'model': 'advanced.project.task', 'type': 'project_gantt',
                'arch': '<project_gantt date_start="nope" date_stop="date_end"/>',
            })
        action = self._project().action_open_gantt()
        self.assertEqual(action['views'][0][1], 'project_gantt')

    def test_link_types(self):
        project = self._project()
        a, b, c = (self._task(project, name=name) for name in 'ABC')
        Task = self.env['advanced.project.task']
        # linking on the form makes an End to Start link
        a.child_ids = [(4, b.id)]
        self.assertEqual(a.child_link_ids.child_id, b)
        self.assertEqual(a.child_link_ids.link_type, 'finish_start')
        # linking on the Gantt chart from a start or end to a start or end
        Task.gantt_link_tasks(a.id, c.id, 'start_start')
        self.assertEqual(c.parent_ids, a)
        data = {(d['parent'], d['child']): d['type'] for d in Task.gantt_link_data((a | b | c).ids)}
        self.assertEqual(data, {(a.id, b.id): 'finish_start', (a.id, c.id): 'start_start'})
        Task.gantt_link_tasks(a.id, b.id, 'finish_finish')
        self.assertEqual(a.child_link_ids.filtered(lambda l: l.child_id == b).link_type, 'finish_finish')
        with self.assertRaises(ValueError):
            Task.gantt_link_tasks(a.id, b.id, 'sideways')
        # unlinking from either side removes the link record
        c.parent_ids = [(3, a.id)]
        self.assertEqual(a.child_link_ids.child_id, b)
        # copies and projects from templates keep each link's kind
        copy = project.copy()
        new_a = copy.task_ids.filtered(lambda t: t.name == 'A')
        self.assertEqual(new_a.child_link_ids.link_type, 'finish_finish')
        self.assertEqual(new_a.child_link_ids.child_id.project_id, copy)

    def test_link_reschedule_rules(self):
        """A child scheduled before its parent is moved later by the link's
        rule, keeping its length."""
        project = self._project()
        Task = self.env['advanced.project.task']
        expected = {
            # child starts the day after the parent ends
            'finish_start': (date(2026, 3, 11), date(2026, 3, 13)),
            # both start together
            'start_start': (date(2026, 3, 5), date(2026, 3, 7)),
            # both end together
            'finish_finish': (date(2026, 3, 8), date(2026, 3, 10)),
            # the child ends when the parent starts
            'start_finish': (date(2026, 3, 3), date(2026, 3, 5)),
        }
        for link_type, (start, end) in expected.items():
            parent = self._task(project, name='Parent', date_start=date(2026, 3, 5), date_end=date(2026, 3, 10))
            child = self._task(project, name='Child', date_start=date(2026, 3, 1), date_end=date(2026, 3, 3))
            proposal = Task.gantt_link_tasks(parent.id, child.id, link_type)
            self.assertTrue(proposal, link_type)
            self.assertIn('“Child” is scheduled before its parent “Parent”', proposal['message'])
            self.assertEqual(proposal['moves'][0]['from'], '01/03/2026 – 03/03/2026')
            Task.gantt_reschedule_link(parent.id, child.id)
            self.assertEqual((child.date_start, child.date_end), (start, end), link_type)
            # now it follows: nothing more to offer
            self.assertFalse(child.parent_ids.child_link_ids.filtered(
                lambda l: l.child_id == child)._gantt_reschedule_proposal())
        # a child already after its parent is left alone
        parent = self._task(project, date_start=date(2026, 3, 5), date_end=date(2026, 3, 10))
        later = self._task(project, date_start=date(2026, 3, 20), date_end=date(2026, 3, 21))
        self.assertFalse(Task.gantt_link_tasks(parent.id, later.id, 'finish_start'))
        # tasks without dates are never rescheduled
        self.assertFalse(Task.gantt_link_tasks(parent.id, self._task(project).id, 'finish_start'))

    def test_link_reschedule_pushes_later_tasks(self):
        project = self._project()
        Task = self.env['advanced.project.task']
        design = self._task(project, name='Design', date_start=date(2026, 3, 1), date_end=date(2026, 3, 10))
        build = self._task(project, name='Build', date_start=date(2026, 3, 2), date_end=date(2026, 3, 4))
        test = self._task(project, name='Test', date_start=date(2026, 3, 5), date_end=date(2026, 3, 6))
        launch = self._task(project, name='Launch', date_end=date(2026, 3, 30), is_milestone=True)
        build.child_ids = [(4, test.id), (4, launch.id)]  # End to Start
        proposal = Task.gantt_link_tasks(design.id, build.id, 'finish_start')
        # Build moves to 11–13/03, so Test follows from 14/03; Launch is late enough already
        self.assertEqual([m['name'] for m in proposal['moves']], ['Build', 'Test'])
        self.assertEqual(proposal['moves'][1]['to'], '14/03/2026 – 15/03/2026')
        Task.gantt_reschedule_link(design.id, build.id)
        self.assertEqual((build.date_start, build.date_end), (date(2026, 3, 11), date(2026, 3, 13)))
        self.assertEqual((test.date_start, test.date_end), (date(2026, 3, 14), date(2026, 3, 15)))
        self.assertEqual(launch.date_end, date(2026, 3, 30))
        self.assertFalse(launch.date_start)

    def test_existing_links_get_link_records(self):
        project = self._project()
        a, b = (self._task(project, name=name) for name in 'AB')
        a.child_ids = [(4, b.id)]
        a.child_link_ids.unlink()  # as before link types existed
        self.env['advanced.project.task']._sync_all_links()
        self.assertEqual(a.child_link_ids.link_type, 'finish_start')

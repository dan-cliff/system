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
        ids = [w['id'] for w in data['widgets']][::-1]
        project.overview_resequence(ids)
        self.assertEqual(project.overview_widget_ids.ids, ids)
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

        publisher = self._user('ap_publisher', 'edit_own')
        with self.assertRaises(AccessError):
            update.with_user(publisher).action_publish()
        update.with_user(self.admin).action_publish()
        self.assertEqual(update.state, 'published')
        self.assertIn('Done task', update.body_html)
        self.assertIn('All good', update.body_html)
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

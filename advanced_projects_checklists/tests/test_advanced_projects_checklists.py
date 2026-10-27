from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdvancedProjectsChecklists(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.template = cls.env['checklist.template'].create({
            'name': 'Site Handover', 'project_available': True,
            'question_ids': [(0, 0, {'name': 'Keys handed over', 'question_type': 'boolean'})],
        })
        cls.project = cls.env['advanced.project'].create({'name': 'Shed Build'})
        cls.task = cls.env['advanced.project.task'].create({
            'name': 'Hand over', 'project_id': cls.project.id, 'date_end': date(2026, 6, 30),
            'checklist_template_id': cls.template.id,
        })

    def test_required_checklist_completes_the_task(self):
        action = self.task.action_start_checklist()
        checklist = self.env['checklist.checklist'].browse(action['res_id'])
        self.assertEqual(checklist.template_id, self.template)
        self.assertEqual((checklist.advanced_task_id, checklist.advanced_project_id), (self.task, self.project))
        self.assertEqual(checklist.date_due, date(2026, 6, 30))
        # started once: the button opens the same checklist again
        self.assertEqual(self.task.action_start_checklist()['res_id'], checklist.id)
        self.assertEqual(self.task.checklist_count, 1)
        self.assertEqual(self.project.checklist_done_count, 0)
        checklist.action_complete()
        self.assertEqual(self.task.stage_category, 'done')
        self.project.invalidate_recordset(['checklist_done_count'])
        self.assertEqual(self.project.checklist_done_count, 1)
        listed = self.env['checklist.checklist'].search(self.project.action_open_checklists()['domain'])
        self.assertEqual(listed, checklist)

    def test_other_checklists_leave_the_task_open(self):
        other = self.env['checklist.template'].create({'name': 'Toolbox Talk'})
        checklist = self.env['checklist.checklist'].create({
            'template_id': other.id, 'advanced_task_id': self.task.id, 'user_id': self.env.user.id})
        checklist.action_complete()
        self.assertNotEqual(self.task.stage_category, 'done')

    def test_task_without_required_checklist(self):
        task = self.env['advanced.project.task'].create({'name': 'Tidy up', 'project_id': self.project.id})
        with self.assertRaises(UserError):
            task.action_start_checklist()
        self.assertEqual(task._fields['checklist_template_id'].domain, [('project_available', '=', True)])

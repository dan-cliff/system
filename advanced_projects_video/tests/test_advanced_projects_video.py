from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdvancedProjectsVideo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.production = cls.env['video.production'].create({
            'name': 'Spring Lambing Vlog', 'date_planned_publish': date(2026, 4, 1)})
        cls.internal = cls.env.ref('advanced_projects.project_type_internal')

    def _wizard(self, **vals):
        return self.env['video.production.project.link'].create(dict({'production_id': self.production.id}, **vals))

    def test_create_internal_project(self):
        action = self._wizard(mode='create').action_confirm()
        project = self.env['advanced.project'].browse(action['res_id'])
        self.assertEqual(self.production.project_id, project)
        self.assertTrue(project.is_internal)
        self.assertEqual(project.name, 'Spring Lambing Vlog')
        self.assertEqual(project.date_end, date(2026, 4, 1))
        self.assertEqual(project.video_production_count, 1)

    def test_create_from_template_stays_internal(self):
        template = self.env.ref('advanced_projects.template_customer_onboarding')
        action = self._wizard(mode='create', template_id=template.id).action_confirm()
        project = self.env['advanced.project'].browse(action['res_id'])
        self.assertTrue(project.is_internal)
        self.assertEqual(len(project.task_ids), len(template.task_ids))

    def test_link_existing_internal_only(self):
        existing = self.env['advanced.project'].create({'name': 'Channel', 'project_type_id': self.internal.id})
        self._wizard(mode='link', project_id=existing.id).action_confirm()
        self.assertEqual(self.production.project_id, existing)
        external = self.env['advanced.project'].create({'name': 'Customer job'})
        with self.assertRaises(ValidationError):
            self.production.project_id = external

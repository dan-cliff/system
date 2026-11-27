from datetime import date

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAdvancedProjectsRisk(TransactionCase):

    def test_new_risk_assessment_for_project(self):
        env = self.env(context=dict(self.env.context, tracking_disable=True))
        colleague = new_test_user(env, 'apr_colleague', groups='base.group_user')
        project = env['advanced.project'].create({'name': 'Open Day', 'date_start': date(2026, 5, 2)})
        env['advanced.project.collaborator'].create({
            'project_id': project.id, 'partner_id': colleague.partner_id.id, 'collaborator_type': 'colleague'})
        action = project.action_new_risk_assessment()
        assessment = env['risk.assessment'].browse(action['res_id'])
        self.assertEqual(assessment.advanced_project_id, project)
        self.assertEqual(assessment.name, 'Open Day – Risk Assessment')
        self.assertEqual(assessment.activity_start.date(), date(2026, 5, 2))
        self.assertIn(colleague, assessment.collaborator_ids)
        self.assertEqual(project.risk_assessment_count, 1)
        listed = env['risk.assessment'].search(project.action_open_risk_assessments()['domain'])
        self.assertEqual(listed, assessment)

import re

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged

from .common import AdvancedProjectCommon


@tagged('post_install', '-at_install')
class TestAdvancedProjectRating(AdvancedProjectCommon, HttpCase):

    def test_rating_requested_when_task_done(self):
        project = self._project(self.admin, partner_id=self.customer.id)
        task = self._task(project, request_rating=True)
        self.assertEqual(task.rating_partner_id, self.customer)  # the project's customer by default
        plain = self._task(project)
        (task | plain).stage_id = self.stage_done
        rating = self.env['advanced.project.rating'].search([('project_id', '=', project.id)])
        self.assertEqual(len(rating), 1)
        self.assertEqual((rating.task_id, rating.partner_id, rating.state), (task, self.customer, 'requested'))
        self.assertIn(f'/my/projects/rating/{rating.id}?access_token=', rating.rating_url)
        # done again later: asked only once
        task.stage_id = self.stage_todo
        task.stage_id = self.stage_done
        self.assertEqual(self.env['advanced.project.rating'].search_count([('task_id', '=', task.id)]), 1)

        with self.assertRaises(UserError):
            rating._submit('9')
        rating._submit('4', 'Great work')
        self.assertEqual((rating.state, rating.score, rating.score_value), ('done', '4', 4))
        self.assertTrue(rating.date_rated)
        self.env['advanced.project.rating'].create({'project_id': project.id, 'score': '2'})
        self.assertEqual(project.project_rating_count, 2)
        self.assertEqual(project.project_rating_avg, 3.0)

    def test_rating_portal_link(self):
        project = self._project(self.admin, partner_id=self.customer.id)
        rating = self.env['advanced.project.rating'].create({
            'project_id': project.id, 'partner_id': self.customer.id, 'state': 'requested'})
        # without the link's token, no rating page
        self.assertNotIn('How did we do?', self.url_open(f'/my/projects/rating/{rating.id}').text)
        page = self.url_open(rating.rating_url.replace(rating.get_base_url(), ''))
        self.assertIn('How did we do?', page.text)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        self.url_open(f'/my/projects/rating/{rating.id}', data={
            'access_token': rating.access_token, 'score': '5', 'feedback': 'Lovely', 'csrf_token': csrf,
        })
        rating.invalidate_recordset()
        self.assertEqual((rating.state, rating.score, rating.feedback), ('done', '5', 'Lovely'))

    def test_customers_see_only_their_ratings(self):
        project = self._project(self.admin, partner_id=self.customer.id)
        user = new_test_user(self.env, 'apr_customer', groups='advanced_projects.group_advanced_project_customer',
                             partner_id=self.customer.id)
        self.env['advanced.project.collaborator'].create({
            'project_id': project.id, 'partner_id': self.customer.id, 'collaborator_type': 'customer'})
        Rating = self.env['advanced.project.rating']
        mine = Rating.create({'project_id': project.id, 'partner_id': self.customer.id, 'score': '5'})
        other = Rating.create({'project_id': project.id, 'score': '1'})
        self.assertEqual(Rating.with_user(user).search([('project_id', '=', project.id)]), mine)
        with self.assertRaises(AccessError):
            other.with_user(user).read(['score'])

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdvancedProjectsDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.project = cls.env['advanced.project'].create({'name': 'Alpha'})
        cls.other = cls.env['advanced.project'].create({'name': 'Beta'})
        Task = cls.env['advanced.project.task']
        Task.create([{'name': 'A1', 'project_id': cls.project.id}, {'name': 'A2', 'project_id': cls.project.id},
                     {'name': 'B1', 'project_id': cls.other.id}])
        # only this test's dashboard is available in every project
        cls.env['custom.dashboard'].search([('show_in_projects', '=', True)]).show_in_projects = False
        cls.dashboard = cls.env['custom.dashboard'].create({'name': 'Delivery', 'show_in_projects': True})
        widget = cls.env['custom.dashboard.widget'].new({
            'dashboard_id': cls.dashboard.id,
            'type_id': cls.env.ref('custom_dashboard.widget_type_kpi').id,
            'name': 'Tasks',
            'model_id': cls.env['ir.model']._get('advanced.project.task').id,
            'domain': "[('project_id.name', 'in', ['Alpha', 'Beta'])]",
        })
        widget._onchange_model_id_project()
        cls.widget = cls.env['custom.dashboard.widget'].create(widget._convert_to_write(widget._cache))

    def test_project_field_guessed(self):
        self.assertEqual(self.widget.project_field_path, 'project_id')

    def test_filtered_only_when_opened_from_a_project(self):
        self.assertEqual(self.widget.get_widget_data()[self.widget.id]['value'], 3)
        from_project = self.widget.with_context(advanced_project_id=self.project.id)
        self.assertEqual(from_project.get_widget_data()[self.widget.id]['value'], 2)

    def test_project_opens_its_dashboards(self):
        self.assertEqual(self.project.dashboard_count, 1)
        action = self.project.action_open_dashboards()
        self.assertEqual(action['params']['advanced_project_id'], self.project.id)
        self.assertEqual(action['params']['dashboard_id'], self.dashboard.id)
        self.dashboard.show_in_projects = False
        self.project.dashboard_ids = self.dashboard
        self.assertEqual(self.project.dashboard_count, 1)
        self.assertEqual(self.other.dashboard_count, 0)

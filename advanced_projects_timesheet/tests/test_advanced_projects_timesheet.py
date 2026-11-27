from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAdvancedProjectsTimesheet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.worker = new_test_user(cls.env, 'apt_worker', groups='base.group_user', name='Sam Worker')
        cls.project = cls.env['advanced.project'].create({'name': 'Shed'})
        cls.task = cls.env['advanced.project.task'].create({'name': 'Roof', 'project_id': cls.project.id})
        cls.other = cls.env['advanced.project'].create({'name': 'Other'})
        cls.sheet = cls.env['advanced.timesheet'].create({'user_id': cls.worker.id})

    def _line(self, hours, **vals):
        return self.env['advanced.timesheet.line'].create(dict({
            'sheet_id': self.sheet.id, 'date': self.sheet.date_start, 'unit_amount': hours}, **vals))

    def test_hours_roll_up(self):
        on_task = self._line(3.5, advanced_task_id=self.task.id)
        self.assertEqual(on_task.advanced_project_id, self.project)
        self._line(1.0, advanced_project_id=self.project.id)
        self._line(2.0, advanced_project_id=self.other.id)
        self.assertEqual(self.task.timesheet_hours, 3.5)
        self.assertEqual(self.project.timesheet_hours, 4.5)
        action = self.project.action_open_timesheet_entries()
        self.assertEqual(self.env['advanced.timesheet.line'].search(action['domain']).mapped('unit_amount'), [3.5, 1.0])
        with self.assertRaises(ValidationError):
            self._line(1.0, advanced_project_id=self.other.id, advanced_task_id=self.task.id)

    def test_grid_rows_per_project_task(self):
        self.assertIn('advanced_task_id', self.env['advanced.timesheet.line']._grid_row_fields())
        self._line(2.0, advanced_task_id=self.task.id)
        self._line(1.0, advanced_project_id=self.project.id)
        rows = self.sheet.get_grid_data()['rows']
        self.assertEqual(len(rows), 2)

    def test_budget_hours_worked(self):
        self.env['advanced.project.budget.line'].create({'project_id': self.project.id, 'allocated_hours': 4})
        self._line(3.0, advanced_task_id=self.task.id)
        self.assertEqual((self.project.allocated_hours, self.project.timesheet_hours), (4, 3))
        self._line(2.0, advanced_project_id=self.project.id)
        self.project.invalidate_recordset(['timesheet_hours'])
        self.assertEqual(self.project.timesheet_hours, 5)

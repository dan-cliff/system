from odoo import _, fields, models
from odoo.addons.advanced_projects.models.advanced_project_task_filter import format_hours


def _hours_by(records, field_name):
    """Hours worked per record of ``field_name``. Read as superuser: everyone
    who can open a project sees how many hours went into it, while the
    entries themselves stay behind the timesheet permissions."""
    Line = records.env['advanced.timesheet.line'].sudo()
    groups = Line._read_group([(field_name, 'in', records.ids)], [field_name], ['unit_amount:sum'])
    return {record.id: hours for record, hours in groups}


def _entries_action(env, name, domain, context):
    action = env['ir.actions.act_window']._for_xml_id(
        'advanced_projects_timesheet.action_advanced_timesheet_line_project')
    action.update({'name': name, 'domain': domain, 'context': context})
    return action


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    timesheet_hours = fields.Float('Hours Worked', compute='_compute_timesheet_hours',
                                   help='Hours booked on timesheets to the project and its tasks.')

    def _compute_timesheet_hours(self):
        hours = _hours_by(self, 'advanced_project_id')
        for project in self:
            project.timesheet_hours = hours.get(project.id, 0.0)

    def action_open_timesheet_entries(self):
        self.ensure_one()
        return _entries_action(self.env, _('%s – Hours', self.name), [('advanced_project_id', '=', self.id)],
                               {'search_default_group_task': 1})

    def _budget_overview_values(self):
        values = super()._budget_overview_values()
        worked, allocated = self.timesheet_hours, self.allocated_hours
        values['hours'].update({
            'worked': format_hours(worked),
            'worked_percent': min(100, round(100 * worked / allocated)) if allocated else 0,
            'over_worked': worked > allocated > 0,
        })
        return values


class AdvancedProjectTask(models.Model):
    _inherit = 'advanced.project.task'

    timesheet_hours = fields.Float('Hours Worked', compute='_compute_timesheet_hours',
                                   help='Hours booked on timesheets to the task.')

    def _compute_timesheet_hours(self):
        hours = _hours_by(self, 'advanced_task_id')
        for task in self:
            task.timesheet_hours = hours.get(task.id, 0.0)

    def action_open_timesheet_entries(self):
        self.ensure_one()
        return _entries_action(self.env, _('%s – Hours', self.name), [('advanced_task_id', '=', self.id)],
                               {'search_default_group_person': 1})

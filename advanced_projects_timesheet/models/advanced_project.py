from odoo import _, fields, models


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

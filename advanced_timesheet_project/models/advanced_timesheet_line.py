# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdvancedTimesheetLine(models.Model):
    _inherit = 'advanced.timesheet.line'

    project_id = fields.Many2one('project.project', string='Project', index=True)
    task_id = fields.Many2one(
        'project.task', string='Task', index=True,
        domain="[('project_id', '=?', project_id)]",
    )

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id.project_id:
            self.project_id = self.task_id.project_id

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False

    @api.model
    def _grid_row_fields(self):
        return ['project_id', 'task_id'] + super()._grid_row_fields()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._set_work_type_from_project()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'project_id' in vals or 'work_type_id' in vals:
            self._set_work_type_from_project()
        return res

    def _set_work_type_from_project(self):
        """Give entries booked to a project without a work type the project's Work Type."""
        WorkType = self.env['advanced.timesheet.work.type'].sudo().with_context(active_test=False)
        for project in self.filtered(lambda l: l.project_id and not l.work_type_id).project_id:
            name = project.sudo().name
            work_type = WorkType.search([('name', '=', name)], limit=1) or WorkType.create({'name': name})
            lines = self.filtered(lambda l: l.project_id == project and not l.work_type_id)
            lines.with_context(advanced_timesheet_sync=True).write({'work_type_id': work_type.id})

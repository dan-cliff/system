from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AdvancedTimesheetLine(models.Model):
    _inherit = 'advanced.timesheet.line'

    advanced_project_id = fields.Many2one(
        'advanced.project', string='Project', index='btree_not_null', ondelete='restrict',
        domain=[('is_template', '=', False)],
        help='The project the hours were worked on (filled in from the task).')
    advanced_task_id = fields.Many2one(
        'advanced.project.task', string='Project Task', index='btree_not_null', ondelete='restrict',
        domain="[('project_id', '=', advanced_project_id)] if advanced_project_id else [('is_template', '=', False)]")

    @api.onchange('advanced_task_id')
    def _onchange_advanced_task_id(self):
        if self.advanced_task_id:
            self.advanced_project_id = self.advanced_task_id.project_id

    @api.onchange('advanced_project_id')
    def _onchange_advanced_project_id(self):
        if self.advanced_task_id and self.advanced_task_id.project_id != self.advanced_project_id:
            self.advanced_task_id = False

    @api.constrains('advanced_project_id', 'advanced_task_id')
    def _check_advanced_task_project(self):
        for line in self:
            if line.advanced_task_id and line.advanced_task_id.project_id != line.advanced_project_id:
                raise ValidationError(_('The task "%s" belongs to another project.', line.advanced_task_id.name))

    @api.model
    def _grid_row_fields(self):
        return ['advanced_project_id', 'advanced_task_id'] + super()._grid_row_fields()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._project_from_task(vals)
        return super().create(vals_list)

    def write(self, vals):
        return super().write(self._project_from_task(dict(vals)))

    def _project_from_task(self, vals):
        if vals.get('advanced_task_id') and not vals.get('advanced_project_id'):
            # sudo: the task's project, for people who can book time but not open the project
            vals['advanced_project_id'] = self.env['advanced.project.task'].sudo().browse(
                vals['advanced_task_id']).project_id.id
        return vals

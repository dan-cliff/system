from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('project', 'Project')], ondelete={'project': 'set default'},
    )
    project_id = fields.Many2one(
        'advanced.project', string='Project', ondelete='cascade', index='btree_not_null',
        domain=[('is_template', '=', False)],
    )
    project_task_id = fields.Many2one(
        'advanced.project.task', string='Project Task', ondelete='cascade', index='btree_not_null',
        domain="[('project_id', '=', project_id)] if project_id else [('is_template', '=', False)]",
    )

    @api.model
    def _action_sources(self):
        # the task first: an action raised from a task also names its project
        return super()._action_sources() + [('project_task_id', 'project'), ('project_id', 'project')]

    def _action_source_parent(self, field_name, record):
        # Company and Organisation come from the project.
        if field_name == 'project_task_id':
            return record.project_id
        return super()._action_source_parent(field_name, record)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('project_task_id') and not vals.get('project_id'):
                vals['project_id'] = self.env['advanced.project.task'].browse(vals['project_task_id']).project_id.id
        if any(vals.get('project_id') or vals.get('project_task_id') for vals in vals_list):
            self._check_project_employee()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('project_task_id') and 'project_id' not in vals:
            vals = dict(vals, project_id=self.env['advanced.project.task'].browse(vals['project_task_id']).project_id.id)
        if vals.get('project_id') or vals.get('project_task_id'):
            self._check_project_employee()
        return super().write(vals)

    def _check_project_employee(self):
        """Only employees raise actions on projects (never portal users)."""
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(_('Only employees can raise actions on projects.'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_task_id and self.project_task_id.project_id != self.project_id:
            self.project_task_id = False

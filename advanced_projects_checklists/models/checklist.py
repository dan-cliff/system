from odoo import fields, models


class ChecklistTemplate(models.Model):
    _inherit = 'checklist.template'

    project_available = fields.Boolean(
        'Available in Projects',
        help='Project tasks can require this checklist: completing it for the task marks the task as done.')


class ChecklistChecklist(models.Model):
    _inherit = 'checklist.checklist'

    advanced_task_id = fields.Many2one(
        'advanced.project.task', string='Project Task', tracking=True, index='btree_not_null',
        ondelete='set null')
    advanced_project_id = fields.Many2one(
        related='advanced_task_id.project_id', string='Project', store=True, index='btree_not_null')

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'done':
            self._complete_project_tasks()
        return res

    def _complete_project_tasks(self):
        """Completing a task's Required Checklist marks the task as done."""
        done_stage = self.env['advanced.project.task.stage'].sudo().search([('category', '=', 'done')], limit=1)
        if not done_stage:
            return
        # sudo: a workflow step, done for whoever completes the checklist
        tasks = self.sudo().filtered(
            lambda c: c.state == 'done' and c.advanced_task_id
            and c.advanced_task_id.checklist_template_id == c.template_id
        ).advanced_task_id.filtered(lambda t: t.stage_category not in ('done', 'cancelled'))
        if tasks:
            tasks.write({'stage_id': done_stage.id})

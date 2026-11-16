from odoo import api, fields, models


class AdvancedExpense(models.Model):
    _inherit = 'advanced.expense'

    project_id = fields.Many2one('project.project', string='Project', index='btree_not_null', tracking=True,
                                 check_company=True,
                                 domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    task_id = fields.Many2one('project.task', string='Task', index='btree_not_null', check_company=True,
                              domain="[('project_id', '=', project_id)]")

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id:
            self.project_id = self.task_id.project_id

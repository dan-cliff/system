from odoo import api, fields, models


class RiskAssessmentLine(models.Model):
    _name = 'risk.assessment.line'
    _inherit = ['risk.line.mixin']
    _description = 'Risk Assessment Line'
    _order = 'sequence, id'
    _form_view_xmlid = 'risk_management.view_risk_assessment_line_form'

    assessment_id = fields.Many2one('risk.assessment', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    source_template_line_id = fields.Many2one(
        'risk.template.line', string='Source Template Risk', copy=False,
    )
    todo_ids = fields.Many2many(
        'project.task', 'risk_assessment_line_task_rel', 'line_id', 'task_id',
        string='Actions',
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._create_todos_from_template_actions()
        return lines

    def _create_todos_from_template_actions(self):
        for line in self.filtered(lambda l: l.source_template_line_id and not l.todo_ids):
            for action in line.source_template_line_id.standard_action_ids:
                vals = {'name': action.name, 'description': action.description}
                if line.assessment_id.assessor_id:
                    vals['user_ids'] = [(4, line.assessment_id.assessor_id.id)]
                task = self.env['project.task'].create(vals)
                line.todo_ids = [(4, task.id)]

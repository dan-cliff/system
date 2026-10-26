from odoo import api, fields, models


class RiskAssessmentLine(models.Model):
    _name = 'risk.assessment.line'
    _inherit = ['risk.line.mixin']
    _description = 'Risk Assessment Line'
    _order = 'sequence, id'
    _form_view_xmlid = 'risk_management.view_risk_assessment_line_form'
    _ai_parent_field = 'assessment_id'
    _ai_actions_field = 'action_ids'

    assessment_id = fields.Many2one('risk.assessment', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    source_template_line_id = fields.Many2one(
        'risk.template.line', string='Source Template Risk', copy=False,
    )
    action_ids = fields.One2many(
        'risk.assessment.action', 'line_id', string='Actions', copy=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._create_actions_from_template()
        return lines

    def _create_actions_from_template(self):
        for line in self.filtered(lambda l: l.source_template_line_id and not l.action_ids):
            line.action_ids = [
                (0, 0, line._action_vals(action.name, action.description))
                for action in line.source_template_line_id.standard_action_ids
            ]

    def _action_vals(self, name, description):
        """Values of an Action on this risk, assigned to the Risk Assessment Owner."""
        self.ensure_one()
        return {
            'name': name,
            'description': description,
            'user_id': self.assessment_id.assessor_id.id or self.env.user.id,
        }

    def _ai_risk_action_vals(self, actions):
        # Same as Standard Actions pulled in from a template: Actions for the Risk Assessment Owner.
        return {'action_ids': [
            (0, 0, self._action_vals(action['name'].strip(), (action.get('description') or '').strip()))
            for action in actions
        ]}

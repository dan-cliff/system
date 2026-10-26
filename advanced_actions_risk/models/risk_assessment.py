from odoo import api, fields, models
from odoo.tools import plaintext2html


class RiskAssessmentLine(models.Model):
    _inherit = 'risk.assessment.line'

    action_ids = fields.One2many('advanced.action', 'risk_line_id', string='Actions', copy=True)

    def _action_vals(self, name, description):
        """Values of an Action on this risk, assigned to the Risk Assessment Owner."""
        self.ensure_one()
        user = self.assessment_id.assessor_id or self.env.user
        return {
            'name': name,
            'description': plaintext2html(description) if description else False,
            'user_ids': [(6, 0, user.ids)],
        }


class RiskAssessment(models.Model):
    _inherit = 'risk.assessment'

    action_ids = fields.One2many('advanced.action', 'risk_assessment_id', string='Actions')

    @api.depends('action_ids.state')
    def _compute_action_open_count(self):
        for assessment in self:
            assessment.action_open_count = len(
                assessment.action_ids.filtered(lambda action: action.state in ('open', 'in_progress'))
            )

    def action_open_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'views': [
                (self.env.ref('advanced_actions_risk.view_advanced_action_list_risk').id, 'list'),
                (False, 'kanban'), (False, 'form'),
            ],
            'domain': [('risk_assessment_id', '=', self.id)],
            'context': {'search_default_open': 1},
        }

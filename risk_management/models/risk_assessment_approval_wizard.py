from markupsafe import Markup

from odoo import fields, models


class RiskAssessmentApprovalWizard(models.TransientModel):
    _name = 'risk.assessment.approval.wizard'
    _description = 'Risk Assessment Approval'

    assessment_id = fields.Many2one('risk.assessment', required=True)
    decision = fields.Selection(
        [('approved', 'Approve'), ('rejected', 'Reject')],
        required=True, default='approved',
    )
    comment = fields.Text(help='Optional note, e.g. why this was rejected.')

    def action_confirm(self):
        self.ensure_one()
        assessment = self.assessment_id
        assessment._check_can_approve()
        if self.decision == 'approved':
            assessment.stage_id = assessment._get_stage('approved')
            body = Markup('Risk Assessment <b>approved</b> by {}.').format(self.env.user.name)
        else:
            assessment.stage_id = assessment._get_stage('in_progress')
            body = Markup('Risk Assessment <b>rejected</b> by {} and returned to In Progress.').format(
                self.env.user.name
            )
        if self.comment:
            body += Markup('<br/>{}').format(self.comment)
        assessment.message_post(body=body)

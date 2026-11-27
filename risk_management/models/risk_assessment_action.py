from odoo import fields, models


class RiskAssessmentAction(models.Model):
    _name = 'risk.assessment.action'
    _description = 'Risk Assessment Action'
    _order = 'date_deadline, sequence, id'
    _org_parent_field = 'assessment_id'

    line_id = fields.Many2one(
        'risk.assessment.line', string='Risk', required=True, ondelete='cascade', index=True,
    )
    assessment_id = fields.Many2one(
        related='line_id.assessment_id', string='Risk Assessment', store=True, index=True,
    )
    company_id = fields.Many2one(related='line_id.assessment_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Action', required=True)
    description = fields.Text()
    user_id = fields.Many2one(
        'res.users', string='Assigned To', index=True,
        default=lambda self: self.env.user,
    )
    date_deadline = fields.Date(string='Due Date')
    # Technical state: the "Open Actions" count and the filters depend on it.
    state = fields.Selection(
        [('open', 'Open'), ('done', 'Done'), ('cancelled', 'Cancelled')],
        string='Status', default='open', required=True,
    )

    def action_mark_done(self):
        self.write({'state': 'done'})

    def action_reopen(self):
        self.write({'state': 'open'})

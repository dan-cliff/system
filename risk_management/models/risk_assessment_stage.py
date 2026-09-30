from odoo import fields, models


class RiskAssessmentStage(models.Model):
    _name = 'risk.assessment.stage'
    _description = 'Risk Assessment Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    stage_type = fields.Selection(
        [
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('submitted', 'Submitted for Approval'),
            ('approved', 'Approved'),
            ('done', 'Completed'),
        ],
        required=True,
        help='What this stage represents in the approval workflow. Drives which buttons are '
             'available on a Risk Assessment sitting in this stage - keep exactly one stage '
             'per type for the workflow buttons to behave predictably.',
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A stage with this name already exists.',
    )

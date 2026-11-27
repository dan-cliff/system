from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('risk', 'Risk Management')], ondelete={'risk': 'set default'},
    )
    risk_line_id = fields.Many2one(
        'risk.assessment.line', string='Risk', ondelete='cascade', index='btree_not_null',
    )
    risk_assessment_id = fields.Many2one(
        related='risk_line_id.assessment_id', string='Risk Assessment', store=True, index='btree_not_null',
    )

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [('risk_line_id', 'risk')]

    def _action_source_parent(self, field_name, record):
        # A risk's Company and Organisation are its Risk Assessment's.
        if field_name == 'risk_line_id':
            return record.assessment_id
        return super()._action_source_parent(field_name, record)

    def _action_source(self):
        # Shown and opened as the Risk Assessment, which is where risks are edited.
        field_name, record = super()._action_source()
        if field_name == 'risk_line_id':
            return 'risk_assessment_id', record.assessment_id
        return field_name, record

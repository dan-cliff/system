from odoo import fields, models


class RiskTemplateLine(models.Model):
    _name = 'risk.template.line'
    _inherit = ['risk.line.mixin']
    _description = 'Risk Template Line'
    _order = 'sequence, id'
    _form_view_xmlid = 'risk_management.view_risk_template_line_form'

    template_id = fields.Many2one('risk.template', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    standard_action_ids = fields.One2many(
        'risk.template.action', 'template_line_id', string='Standard Actions',
        help='Actions that should always be turned into To-Dos when a Risk Assessment pulls '
             'this risk in from the template.',
    )

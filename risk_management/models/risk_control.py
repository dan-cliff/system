from odoo import api, fields, models

from .risk_ai_mixin import ai_generate_control_description


class RiskControl(models.Model):
    _name = 'risk.control'
    _description = 'Risk Control'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(help='Optional internal reference, e.g. from a control framework.')
    category_id = fields.Many2one('risk.category', string='Risk Category')
    hierarchy_id = fields.Many2one(
        'risk.control.hierarchy', string='Hierarchy of Controls',
    )
    description = fields.Text()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A control with this name already exists.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        controls = super().create(vals_list)
        controls._ai_fill_missing_descriptions()
        return controls

    def _ai_fill_missing_descriptions(self):
        """Best-effort backfill of a detailed description for controls that don't have one."""
        controls = self.filtered(lambda control: not control.description)
        if not controls:
            return
        api_key = self.env['ir.config_parameter'].sudo().get_param('claude_ai_settings.api_key')
        if not api_key:
            return
        for control in controls:
            description = ai_generate_control_description(api_key, control.name)
            if description:
                # sudo: users who may create Controls but not edit them still get the backfill
                control.sudo().description = description

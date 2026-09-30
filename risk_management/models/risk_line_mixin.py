from odoo import api, fields, models


class RiskLineMixin(models.AbstractModel):
    _name = 'risk.line.mixin'
    _description = 'Risk Line Mixin'

    # XML ID of this concrete model's own form view, set by each model that
    # inherits this mixin. Without this, "open full record" navigation (e.g.
    # the expand icon on a one2many dialog) has no view to resolve to and
    # falls back to a bare, auto-generated form showing every raw field.
    _form_view_xmlid = None

    name = fields.Text(string='Risk', required=True)
    unwanted_event = fields.Text(string='Unwanted Event')
    description = fields.Text()
    control_ids = fields.Many2many('risk.control', string='Controls')
    control_summary = fields.Text(string='Controls Summary')

    risk_type_id = fields.Many2one('risk.type', string='Risk Type')
    risk_subtype_id = fields.Many2one(
        'risk.subtype', string='Risk Subtype',
        domain="[('risk_type_id', '=', risk_type_id)]",
    )

    inherent_likelihood_id = fields.Many2one('risk.likelihood', string='Inherent Likelihood')
    inherent_consequence_id = fields.Many2one('risk.consequence', string='Inherent Consequence')
    inherent_risk_score_id = fields.Many2one(
        'risk.score', string='Inherent Risk Matrix Cell', compute='_compute_risk_score_ids', store=True,
    )
    inherent_severity_id = fields.Many2one(
        related='inherent_risk_score_id.severity_id', string='Inherent Severity', store=True, readonly=True,
    )
    inherent_score = fields.Integer(related='inherent_risk_score_id.score', store=True, readonly=True)
    inherent_label = fields.Char(
        related='inherent_risk_score_id.label', string='Inherent Risk', store=True, readonly=True,
    )
    inherent_bg_color = fields.Char(related='inherent_risk_score_id.bg_color', readonly=True)
    inherent_text_color = fields.Char(related='inherent_risk_score_id.text_color', readonly=True)

    residual_likelihood_id = fields.Many2one('risk.likelihood', string='Residual Likelihood')
    residual_consequence_id = fields.Many2one('risk.consequence', string='Residual Consequence')
    residual_risk_score_id = fields.Many2one(
        'risk.score', string='Residual Risk Matrix Cell', compute='_compute_risk_score_ids', store=True,
    )
    residual_severity_id = fields.Many2one(
        related='residual_risk_score_id.severity_id', string='Residual Severity', store=True, readonly=True,
    )
    residual_score = fields.Integer(related='residual_risk_score_id.score', store=True, readonly=True)
    residual_label = fields.Char(
        related='residual_risk_score_id.label', string='Residual Risk', store=True, readonly=True,
    )
    residual_bg_color = fields.Char(related='residual_risk_score_id.bg_color', readonly=True)
    residual_text_color = fields.Char(related='residual_risk_score_id.text_color', readonly=True)

    @api.depends(
        'inherent_likelihood_id', 'inherent_consequence_id',
        'residual_likelihood_id', 'residual_consequence_id',
    )
    def _compute_risk_score_ids(self):
        Score = self.env['risk.score']
        for line in self:
            line.inherent_risk_score_id = line._find_risk_score(
                line.inherent_likelihood_id, line.inherent_consequence_id, Score,
            )
            line.residual_risk_score_id = line._find_risk_score(
                line.residual_likelihood_id, line.residual_consequence_id, Score,
            )

    @api.onchange('risk_type_id')
    def _onchange_risk_type_id(self):
        if self.risk_subtype_id and self.risk_subtype_id.risk_type_id != self.risk_type_id:
            self.risk_subtype_id = False

    def _find_risk_score(self, likelihood, consequence, Score=None):
        Score = Score or self.env['risk.score']
        if likelihood and consequence:
            return Score.search([
                ('likelihood_id', '=', likelihood.id),
                ('consequence_id', '=', consequence.id),
            ], limit=1)
        return Score.browse()

    def get_formview_id(self, access_uid=None):
        if self._form_view_xmlid:
            view = self.env.ref(self._form_view_xmlid, raise_if_not_found=False)
            if view:
                return view.id
        return super().get_formview_id(access_uid=access_uid)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.control_ids._ai_fill_missing_descriptions()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if 'control_ids' in vals:
            self.control_ids._ai_fill_missing_descriptions()
        return result

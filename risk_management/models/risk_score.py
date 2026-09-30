from odoo import api, fields, models


class RiskScore(models.Model):
    _name = 'risk.score'
    _description = 'Risk Score'
    _order = 'likelihood_id, consequence_id'

    likelihood_id = fields.Many2one('risk.likelihood', required=True, ondelete='cascade', index=True)
    consequence_id = fields.Many2one('risk.consequence', required=True, ondelete='cascade', index=True)
    severity_id = fields.Many2one('risk.severity', required=True)
    score = fields.Integer(required=True, help='Numeric risk score for this likelihood/consequence combination.')
    label = fields.Char(
        required=True,
        help='Text shown in the risk matrix cell. Defaults to the severity\'s first letter '
             'and the score, e.g. "L-4" for a Low severity cell scoring 4.',
    )
    bg_color = fields.Char(related='severity_id.bg_color', string='Background Colour', store=True, readonly=True)
    text_color = fields.Char(related='severity_id.text_color', string='Text Colour', store=True, readonly=True)

    _cell_uniq = models.Constraint(
        'unique (likelihood_id, consequence_id)',
        'Only one risk score can be defined per likelihood/consequence combination.',
    )

    @api.onchange('likelihood_id', 'consequence_id', 'severity_id')
    def _onchange_suggest_score_and_label(self):
        if self.likelihood_id and self.consequence_id and not self.score:
            self.score = self.likelihood_id.value * self.consequence_id.value
        if self.severity_id and self.score and not self.label:
            self.label = '%s-%s' % (self.severity_id.name[0].upper(), self.score)

    def _compute_display_name(self):
        for score in self:
            score.display_name = '%s / %s (%s)' % (
                score.likelihood_id.name, score.consequence_id.name, score.label,
            )

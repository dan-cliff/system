from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ModernCrmStage(models.Model):
    _name = 'modern.crm.stage'
    _description = 'CRM Opportunity Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    probability = fields.Float(
        'Probability (%)', default=10.0,
        help='Default probability of closing for opportunities in this stage.')
    forecast_category_id = fields.Many2one(
        'modern.crm.forecast.category', string='Forecast Category',
        help='Default forecast category of opportunities in this stage.')
    is_won = fields.Boolean('Closed Won', help='Opportunities in this stage are won.')
    is_lost = fields.Boolean('Closed Lost', help='Opportunities in this stage are lost.')
    fold = fields.Boolean('Folded in Pipeline')
    guidance = fields.Html(
        'Guidance for Success', translate=True,
        help='Tips shown on opportunities in this stage: what to do to move them on.')

    @api.constrains('is_won', 'is_lost')
    def _check_won_lost(self):
        for stage in self:
            if stage.is_won and stage.is_lost:
                raise ValidationError(self.env._('A stage cannot be both Closed Won and Closed Lost.'))

    @api.constrains('probability')
    def _check_probability(self):
        for stage in self:
            if not 0 <= stage.probability <= 100:
                raise ValidationError(self.env._('The probability must be between 0 and 100.'))

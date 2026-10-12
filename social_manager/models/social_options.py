from odoo import fields, models


class SocialSentiment(models.Model):
    _name = 'social.sentiment'
    _description = 'Comment Sentiment'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    description = fields.Char(help='Shown to the AI to explain when to use this sentiment.')
    active = fields.Boolean(default=True)


class SocialIncomeType(models.Model):
    _name = 'social.income.type'
    _description = 'Monetisation Income Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

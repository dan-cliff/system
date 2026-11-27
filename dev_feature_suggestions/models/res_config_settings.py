from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dev_suggestion_review_first = fields.Boolean(
        'Review New Suggestions First', config_parameter='dev_feature_suggestions.review_first',
        help='New suggestions stay off the website forum until a moderator publishes them. When off, they show '
             'straight away.')
    dev_suggestion_page_title = fields.Char(
        'Forum Title', config_parameter='dev_feature_suggestions.page_title', default='Feature Requests')
    dev_suggestion_page_intro = fields.Char(
        'Forum Introduction', config_parameter='dev_feature_suggestions.page_intro',
        default='Tell us what would make our products better, vote for the ideas that matter to you and follow '
                'their progress.')

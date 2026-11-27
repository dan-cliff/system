from odoo import api, fields, models


class DevFeature(models.Model):
    _inherit = 'dev.feature'

    suggestion_ids = fields.Many2many('dev.suggestion', 'dev_suggestion_feature_rel', 'feature_id', 'suggestion_id',
                                      string='Suggestions', groups='dev_feature_suggestions.group_suggestion_user')
    suggestion_vote_count = fields.Integer('Suggestion Votes', compute='_compute_suggestion_votes',
                                           groups='dev_feature_suggestions.group_suggestion_user',
                                           help='Votes of the suggestions this feature delivers.')

    @api.depends('suggestion_ids.vote_count')
    def _compute_suggestion_votes(self):
        for feature in self:
            feature.suggestion_vote_count = sum(feature.suggestion_ids.mapped('vote_count'))


class DevTicket(models.Model):
    _inherit = 'dev.ticket'

    suggestion_ids = fields.Many2many('dev.suggestion', 'dev_suggestion_ticket_rel', 'ticket_id', 'suggestion_id',
                                      string='Suggestions', groups='dev_feature_suggestions.group_suggestion_user')


class DevRelease(models.Model):
    _inherit = 'dev.release'

    def write(self, vals):
        result = super().write(vals)
        if vals.get('state') == 'core':
            Suggestion = self.env['dev.suggestion'].sudo()
            for release in self:
                suggestions = Suggestion.search(['|', ('feature_ids.release_id', '=', release.id),
                                                 ('ticket_ids.release_id', '=', release.id)])
                suggestions._mark_released(release)
        return result

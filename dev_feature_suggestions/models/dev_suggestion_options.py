"""Option lists of Feature Suggestions, managed under Configuration (CLAUDE.md > Choice fields)."""
from odoo import fields, models


class DevSuggestionCategory(models.Model):
    _name = 'dev.suggestion.category'
    _description = 'Feature Suggestion Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    description = fields.Text(translate=True, help='Shown on the website forum.')
    is_public = fields.Boolean('On Website', default=True,
                               help='Website visitors can browse and post in this category.')


class DevSuggestionStatus(models.Model):
    _name = 'dev.suggestion.status'
    _description = 'Feature Suggestion Status'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    fold = fields.Boolean('Folded in Board')
    is_closed = fields.Boolean('Closed for Votes', help='Suggestions in this status take no more votes.')
    notify_followers = fields.Boolean('Notify Followers', default=True,
                                      help='Tell the suggester and every voter when a suggestion moves here.')
    set_on_release = fields.Boolean('Set When Released',
                                    help='Suggestions move here when a release that delivers them reaches Core Release.')
    website_description = fields.Text('Meaning', translate=True,
                                      help='What the status means, shown to customers on the website.')


class DevSuggestionSource(models.Model):
    _name = 'dev.suggestion.source'
    _description = 'Feature Suggestion Source'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DevSuggestionImportance(models.Model):
    _name = 'dev.suggestion.importance'
    _description = 'Feature Suggestion Importance'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    weight = fields.Integer(default=1, help='How much a vote of this importance adds to the suggestion\'s score.')

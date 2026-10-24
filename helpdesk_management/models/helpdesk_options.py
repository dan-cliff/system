"""Configurable choice lists, managed under Helpdesk > Configuration."""
from random import randint

from odoo import fields, models


class HelpdeskTicketType(models.Model):
    _name = 'helpdesk.ticket.type'
    _description = 'Helpdesk Ticket Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A ticket type with this name already exists.')


class HelpdeskTag(models.Model):
    _name = 'helpdesk.tag'
    _description = 'Helpdesk Tag'
    _order = 'name'

    def _default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(default=_default_color)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A tag with this name already exists.')


class HelpdeskTicketSource(models.Model):
    _name = 'helpdesk.ticket.source'
    _description = 'Helpdesk Ticket Source'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A ticket source with this name already exists.')


class HelpdeskSentiment(models.Model):
    _name = 'helpdesk.sentiment'
    _description = 'Helpdesk Customer Sentiment'
    _order = 'score desc, sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    score = fields.Integer(
        required=True, default=3,
        help='How positive this sentiment is, from 1 (very negative) to 5 (very positive). '
             'Averaged in the sentiment charts.')
    color = fields.Integer('Color Index')

    _name_uniq = models.Constraint('unique (name)', 'A sentiment with this name already exists.')
    _score_range = models.Constraint('CHECK (score BETWEEN 1 AND 5)', 'The score must be between 1 and 5.')

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

# -*- coding: utf-8 -*-
from odoo import fields, models


class MembershipStatus(models.Model):
    _name = 'membership.status'
    _description = 'Membership Status'
    _order = 'sequence, name'

    name = fields.Char(string='Status Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(
        string='Colour',
        default=0,
        help='Kanban colour index (0–11) used for colour-coding lists and badges.',
    )
    fold = fields.Boolean(
        string='Folded in Status Bar',
        default=True,
        help='When enabled, this status is hidden from the membership status bar '
             'unless the membership is currently in this status.',
    )

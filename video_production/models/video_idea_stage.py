# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoIdeaStage(models.Model):
    _name = 'video.idea.stage'
    _description = 'Video Idea Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Folded in Kanban', default=False)
    description = fields.Text(string='Requirements')
    color = fields.Integer(string='Color Index', default=0)
    is_won = fields.Boolean(
        string='Promoted / Won',
        help='Tick this stage if ideas here are approved and promoted to a Production.',
    )

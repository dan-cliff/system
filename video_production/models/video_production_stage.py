# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoProductionStage(models.Model):
    _name = 'video.production.stage'
    _description = 'Video Production Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Folded in Kanban', default=False)
    is_published = fields.Boolean(
        string='Published Stage',
        help='Productions in this stage are considered published.',
    )
    description = fields.Text(string='Stage Description')
    color = fields.Integer(string='Color Index', default=0)

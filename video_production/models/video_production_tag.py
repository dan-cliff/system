# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoProductionTag(models.Model):
    _name = 'video.production.tag'
    _description = 'Video Production Tag'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index', default=0)

    _name_unique = models.Constraint('UNIQUE(name)', 'Tag names must be unique.')

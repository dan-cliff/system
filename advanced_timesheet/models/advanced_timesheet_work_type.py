# -*- coding: utf-8 -*-
from odoo import fields, models


class AdvancedTimesheetWorkType(models.Model):
    _name = 'advanced.timesheet.work.type'
    _description = 'Timesheet Work Type'
    _order = 'sequence, name, id'

    name = fields.Char(string='Work Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

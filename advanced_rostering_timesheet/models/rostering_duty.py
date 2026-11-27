# -*- coding: utf-8 -*-
from odoo import fields, models


class RosteringDuty(models.Model):
    _inherit = 'rostering.duty'

    work_type_id = fields.Many2one('advanced.timesheet.work.type', string='Timesheet Work Type',
                                   help='Work Type of the timesheet entries filled in from shifts on this duty.')


class RosteringLeaveType(models.Model):
    _inherit = 'rostering.leave.type'

    work_type_id = fields.Many2one('advanced.timesheet.work.type', string='Timesheet Work Type',
                                   help='Work Type of the timesheet entries filled in from this leave.')

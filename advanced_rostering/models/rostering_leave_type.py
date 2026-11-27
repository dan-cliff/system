# -*- coding: utf-8 -*-
from odoo import fields, models


class RosteringLeaveType(models.Model):
    """Kinds of leave. Kept simple on purpose: entitlements and balances will
    come from Payroll."""
    _name = 'rostering.leave.type'
    _description = 'Leave Type'
    _order = 'sequence, name, id'

    name = fields.Char(string='Leave Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Colour')
    description = fields.Text(string='Description', translate=True)
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Leave empty to offer the leave type to every company.')

# -*- coding: utf-8 -*-
from odoo import fields, models


class RosteringDuty(models.Model):
    _name = 'rostering.duty'
    _description = 'Duty'
    _order = 'sequence, name, id'

    name = fields.Char(string='Duty', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Colour')
    description = fields.Text(string='Description', translate=True,
                              help='What the person on this duty does, shown with their shifts.')
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Leave empty to offer the duty to every company.')

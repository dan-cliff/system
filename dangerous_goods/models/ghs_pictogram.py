# -*- coding: utf-8 -*-
from odoo import fields, models


class GhsPictogram(models.Model):
    _name = 'ghs.pictogram'
    _description = 'GHS Pictogram'
    _order = 'sequence, code'

    name = fields.Char('Pictogram Name', required=True, translate=True)
    code = fields.Char('GHS Code', size=10, required=True,
                       help='e.g. GHS01, GHS02 … GHS09')
    description = fields.Text('Description', translate=True,
                              help='Hazard types associated with this pictogram.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f'{rec.code} — {rec.name}'))
        return result

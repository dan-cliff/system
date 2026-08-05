# -*- coding: utf-8 -*-
from odoo import fields, models


class GhsHazardStatement(models.Model):
    _name = 'ghs.hazard.statement'
    _description = 'GHS Hazard Statement (H-code)'
    _order = 'code'
    _rec_name = 'code'

    code = fields.Char('H-Code', size=10, required=True, index=True,
                       help='e.g. H200, H300, H400')
    statement = fields.Text('Statement Text', required=True, translate=True)
    hazard_type = fields.Selection([
        ('physical', 'Physical'),
        ('health', 'Health'),
        ('environmental', 'Environmental'),
        ('supplemental', 'Supplemental / EUH'),
    ], string='Hazard Type')
    hazard_class_ids = fields.Many2many(
        'ghs.hazard.class', 'ghs_statement_class_rel',
        'statement_id', 'class_id', string='Associated Hazard Classes')
    active = fields.Boolean(default=True)
    note = fields.Text('Notes')

    def name_get(self):
        result = []
        for rec in self:
            stmt = (rec.statement or '')[:80]
            if len(rec.statement or '') > 80:
                stmt += '…'
            result.append((rec.id, f'{rec.code} — {stmt}'))
        return result

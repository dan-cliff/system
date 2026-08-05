# -*- coding: utf-8 -*-
from odoo import fields, models


class GhsPrecautionaryStatement(models.Model):
    _name = 'ghs.precautionary.statement'
    _description = 'GHS Precautionary Statement (P-code)'
    _order = 'code'
    _rec_name = 'code'

    code = fields.Char('P-Code', size=10, required=True, index=True,
                       help='e.g. P101, P201, P301')
    category = fields.Selection([
        ('general', 'General (P1xx)'),
        ('prevention', 'Prevention (P2xx)'),
        ('response', 'Response (P3xx)'),
        ('storage', 'Storage (P4xx)'),
        ('disposal', 'Disposal (P5xx)'),
    ], string='Category')
    statement = fields.Text('Statement Text', required=True, translate=True)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for rec in self:
            stmt = (rec.statement or '')[:80]
            if len(rec.statement or '') > 80:
                stmt += '…'
            result.append((rec.id, f'{rec.code} — {stmt}'))
        return result

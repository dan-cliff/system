# -*- coding: utf-8 -*-
from odoo import fields, models


class GhsHazardClass(models.Model):
    _name = 'ghs.hazard.class'
    _description = 'GHS Hazard Class'
    _order = 'hazard_type, sequence, id'

    name = fields.Char('Hazard Class Name', required=True, translate=True)
    code = fields.Char('Code', size=30, required=True)
    hazard_type = fields.Selection([
        ('physical', 'Physical Hazard'),
        ('health', 'Health Hazard'),
        ('environmental', 'Environmental Hazard'),
    ], string='Hazard Type', required=True)
    category = fields.Char('Category / Division',
                           help='e.g. Category 1, Type A, Division 1.1')
    description = fields.Text('Description', translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    pictogram_ids = fields.Many2many(
        'ghs.pictogram', 'ghs_class_pictogram_rel',
        'class_id', 'pictogram_id', string='Associated Pictograms')

    def name_get(self):
        result = []
        for rec in self:
            label = f'[{rec.code}] {rec.name}'
            if rec.category:
                label += f' — {rec.category}'
            result.append((rec.id, label))
        return result

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IcamCategory(models.Model):
    """Top-level ICAM investigation category (the four pillars)."""
    _name = 'icam.category'
    _description = 'ICAM Category'
    _order = 'sequence, id'

    name = fields.Char('Category Name', required=True, translate=True)
    code = fields.Char('Code', size=10)
    description = fields.Text('Description / Guidance', translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer('Colour Index')
    active = fields.Boolean(default=True)
    factor_ids = fields.One2many('icam.factor', 'category_id', string='Factors')
    factor_count = fields.Integer(
        'Factor Count', compute='_compute_factor_count', store=True)

    @api.depends('factor_ids')
    def _compute_factor_count(self):
        for rec in self:
            rec.factor_count = len(rec.factor_ids)


class IcamFactor(models.Model):
    """A specific contributing factor within an ICAM category — fully configurable."""
    _name = 'icam.factor'
    _description = 'ICAM Factor'
    _order = 'category_id, sequence, id'

    name = fields.Char('Factor', required=True, translate=True)
    category_id = fields.Many2one(
        'icam.category', string='ICAM Category',
        required=True, ondelete='cascade', index=True)
    category_code = fields.Char(related='category_id.code', string='Category Code', store=True)
    description = fields.Text(
        'Description / Guidance', translate=True,
        help='Explain what this factor covers to assist investigators.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

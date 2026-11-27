# -*- coding: utf-8 -*-
"""Option lists managed under Property › Configuration (CLAUDE.md > Choice fields)."""
from odoo import fields, models


class PropertyCategory(models.Model):
    _name = 'property.category'
    _description = 'Property Category'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)


class PropertyType(models.Model):
    _name = 'property.type'
    _description = 'Property Type'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category_ids = fields.Many2many(
        'property.category', 'property_type_category_rel', 'type_id', 'category_id',
        string='Categories',
        help='The categories this type is offered for. Leave empty to offer it for every category.',
    )


class PropertyStage(models.Model):
    _name = 'property.stage'
    _description = 'Property Status'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean(string='Folded in Kanban')
    is_closed = fields.Boolean(
        string='No Longer Held',
        help='Properties in this status have been sold, handed back or otherwise left the portfolio.',
    )


class PropertyRentFrequency(models.Model):
    _name = 'property.rent.frequency'
    _description = 'Payment Frequency'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    periods_per_year = fields.Float(
        string='Payments per Year', required=True, default=12,
        help='Used to work out annual amounts, e.g. 12 for monthly, 52 for weekly.',
    )


class PropertyRentReviewType(models.Model):
    _name = 'property.rent.review.type'
    _description = 'Rent Review Type'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)


class PropertyContractType(models.Model):
    _name = 'property.contract.type'
    _description = 'Property Contract Type'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

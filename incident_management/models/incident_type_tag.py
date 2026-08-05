# -*- coding: utf-8 -*-
from odoo import fields, models


class IncidentTypeTag(models.Model):
    """Predefined incident categories — supports many-to-many selection so a
    single incident (e.g. a vehicle crash with injuries) can belong to multiple
    categories simultaneously."""
    _name = 'incident.type.tag'
    _description = 'Incident Category'
    _order = 'sequence, id'

    name = fields.Char('Category Name', required=True, translate=True)
    code = fields.Char('Code', required=True, size=30,
                       help="Short code used internally for view conditions.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Colour Index')

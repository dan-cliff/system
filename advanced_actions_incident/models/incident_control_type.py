from odoo import fields, models


class IncidentControlType(models.Model):
    """Hierarchy of Controls classification of a corrective action."""
    _name = 'incident.control.type'
    _description = 'Corrective Action Control Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

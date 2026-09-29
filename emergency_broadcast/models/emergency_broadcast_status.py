from odoo import fields, models


class EmergencyBroadcastStatus(models.Model):
    _name = 'emergency.broadcast.status'
    _description = 'Emergency Broadcast Status'
    _order = 'sequence, name'

    name = fields.Char('Status Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=10)
    color = fields.Integer('Colour Index', default=0,
                           help='Colour used in kanban view (0–11 following Odoo colour palette).')
    active = fields.Boolean('Active', default=True)
    description = fields.Text('Description')

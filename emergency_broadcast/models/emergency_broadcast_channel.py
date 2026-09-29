from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmergencyBroadcastChannel(models.Model):
    _name = 'emergency.broadcast.channel'
    _description = 'Emergency Broadcast Delivery Channel'
    _order = 'sequence, name'

    name = fields.Char('Channel Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)
    technical_type = fields.Selection([
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('popup', 'Popup Notification'),
        ('dialog', 'Dialogue Box'),
    ], string='Technical Type', required=True,
        help='Determines how the message is delivered to recipients.')
    icon = fields.Char('Icon Class', default='fa-bell',
                       help='FontAwesome icon class, e.g. fa-envelope, fa-sms, fa-bell, fa-exclamation-circle.')
    description = fields.Text('Description')

    @api.constrains('technical_type')
    def _check_unique_technical_type(self):
        for record in self:
            domain = [('technical_type', '=', record.technical_type), ('id', '!=', record.id), ('active', '=', True)]
            if self.search_count(domain):
                raise ValidationError(
                    'A channel with technical type "%s" already exists. '
                    'Each technical type can only have one active channel.' % record.technical_type
                )

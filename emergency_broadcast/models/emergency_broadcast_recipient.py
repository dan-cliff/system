from odoo import api, fields, models


class EmergencyBroadcastRecipient(models.Model):
    _name = 'emergency.broadcast.recipient'
    _description = 'Emergency Broadcast Recipient'
    _order = 'user_id'
    _rec_name = 'user_id'

    broadcast_id = fields.Many2one(
        'emergency.broadcast', 'Broadcast', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', 'User', required=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', related='user_id.partner_id', store=True)
    sent_date = fields.Datetime('Sent At', readonly=True)
    acknowledged = fields.Boolean('Acknowledged', default=False)
    acknowledged_date = fields.Datetime('Acknowledged At', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if 'sent_date' not in vals:
                vals['sent_date'] = now
        return super().create(vals_list)

    def action_acknowledge(self):
        """Called from the frontend or manually by an admin."""
        for rec in self:
            if not rec.acknowledged:
                rec.write({
                    'acknowledged': True,
                    'acknowledged_date': fields.Datetime.now(),
                })

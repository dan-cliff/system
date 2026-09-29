from datetime import timedelta

from odoo import api, fields, models


class EmergencyBroadcastUserPresence(models.Model):
    """
    Lightweight presence tracker.  The frontend JS heartbeat pings
    /emergency_broadcast/heartbeat every 60 seconds for each logged-in
    internal user.  This lets 'Logged-In' recipient filtering select only
    users whose client is currently active.
    """
    _name = 'emergency.broadcast.user.presence'
    _description = 'Emergency Broadcast User Presence'
    _rec_name = 'user_id'

    user_id = fields.Many2one(
        'res.users', 'User', required=True, ondelete='cascade', index=True)
    last_seen = fields.Datetime('Last Seen', required=True, default=fields.Datetime.now)

    _user_id_unique = models.Constraint(
        'UNIQUE(user_id)',
        'Each user can only have one presence record.',
    )

    @api.model
    def update_presence(self, user_id=None):
        """Upsert presence record for the given (or current) user."""
        uid = user_id or self.env.uid
        record = self.sudo().search([('user_id', '=', uid)], limit=1)
        now = fields.Datetime.now()
        if record:
            record.write({'last_seen': now})
        else:
            self.sudo().create({'user_id': uid, 'last_seen': now})

    @api.model
    def get_logged_in_user_ids(self, threshold_minutes=10):
        """Return IDs of users seen within the last threshold_minutes minutes."""
        cutoff = fields.Datetime.now() - timedelta(minutes=threshold_minutes)
        records = self.sudo().search([('last_seen', '>=', cutoff)])
        return records.mapped('user_id.id')

    @api.model
    def _gc_old_presence(self):
        """Garbage-collect stale presence records older than 1 hour (called by cron)."""
        cutoff = fields.Datetime.now() - timedelta(hours=1)
        self.sudo().search([('last_seen', '<', cutoff)]).unlink()

from datetime import timedelta

from odoo import api, fields, models


class OfflineAccessSyncLog(models.Model):
    _name = 'offline.access.sync.log'
    _description = 'Offline Access Sync Log'
    _order = 'date desc, id desc'
    _rec_name = 'date'

    date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True, index=True)
    device_id = fields.Many2one('offline.access.device', string='Device', readonly=True,
                                index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', string='User', required=True, readonly=True,
                              index=True, ondelete='cascade')
    duration = fields.Float(string='Duration (s)', digits=(16, 2), readonly=True)
    model_count = fields.Integer(string='Models', readonly=True)
    records_sent = fields.Integer(string='Records Sent', readonly=True,
                                  help='New or changed records sent to the device.')
    records_kept = fields.Integer(string='Records on Device', readonly=True,
                                  help='Records the device keeps for offline use after this sync.')
    # Technical result the sync code sets, so a fixed selection.
    state = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], required=True, default='success', readonly=True, index=True)
    error = fields.Text(readonly=True)

    @api.model
    def _cron_purge(self):
        days = self.env['offline.access.device']._get_offline_access_config()['log_days']
        self.search([('date', '<', fields.Datetime.now() - timedelta(days=days))]).unlink()

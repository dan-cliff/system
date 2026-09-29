from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Emergency Assistance Button ───────────────────────────────────────────
    eb_assistance_status_id = fields.Many2one(
        'emergency.broadcast.status',
        string='Default Status',
        help='Status applied to the auto-generated Emergency Assistance broadcast.')
    eb_assistance_priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Important'),
        ('2', 'Urgent'),
        ('3', 'Critical'),
    ], string='Default Priority', default='3',
        help='Priority applied to the auto-generated Emergency Assistance broadcast.')
    eb_assistance_recipient_filter = fields.Selection([
        ('all', 'All Internal Users'),
        ('company', 'By Company'),
        ('users', 'Specific Users'),
        ('logged_in', 'Logged-In Users Only'),
    ], string='Recipient Filter', default='all',
        help='Who receives the auto-generated Emergency Assistance broadcast.')
    eb_assistance_channel_ids = fields.Many2many(
        'emergency.broadcast.channel',
        'res_config_settings_eb_channel_rel',
        'config_id', 'channel_id',
        string='Delivery Channels',
        help='Channels used when the Emergency Assistance button is pressed.')
    eb_assistance_message = fields.Text(
        'Auto-Message',
        default='Emergency assistance has been requested.',
        help='Message body text for the auto-generated Emergency Assistance broadcast.')

    # ── Load / save via ir.config_parameter ──────────────────────────────────
    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()

        status_id = int(ICP.get_param('emergency_broadcast.assistance_status_id', default=0) or 0)
        res['eb_assistance_status_id'] = status_id or False

        priority = ICP.get_param('emergency_broadcast.assistance_priority', default='3')
        res['eb_assistance_priority'] = priority

        recipient_filter = ICP.get_param(
            'emergency_broadcast.assistance_recipient_filter', default='all')
        res['eb_assistance_recipient_filter'] = recipient_filter

        channel_ids_str = ICP.get_param('emergency_broadcast.assistance_channel_ids', default='')
        channel_ids = []
        if channel_ids_str:
            try:
                channel_ids = [int(x) for x in channel_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                pass
        res['eb_assistance_channel_ids'] = [(6, 0, channel_ids)]

        message = ICP.get_param(
            'emergency_broadcast.assistance_message',
            default='Emergency assistance has been requested.')
        res['eb_assistance_message'] = message

        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()

        ICP.set_param(
            'emergency_broadcast.assistance_status_id',
            str(self.eb_assistance_status_id.id) if self.eb_assistance_status_id else '0')
        ICP.set_param(
            'emergency_broadcast.assistance_priority',
            self.eb_assistance_priority or '3')
        ICP.set_param(
            'emergency_broadcast.assistance_recipient_filter',
            self.eb_assistance_recipient_filter or 'all')
        ICP.set_param(
            'emergency_broadcast.assistance_channel_ids',
            ','.join(str(c) for c in self.eb_assistance_channel_ids.ids))
        ICP.set_param(
            'emergency_broadcast.assistance_message',
            self.eb_assistance_message or 'Emergency assistance has been requested.')

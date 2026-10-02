from odoo import fields, http
from odoo.http import request


class EmergencyBroadcastController(http.Controller):

    @http.route('/emergency_broadcast/acknowledge', type='jsonrpc', auth='user', methods=['POST'])
    def acknowledge(self, recipient_id):
        """Called by the frontend when a user clicks Acknowledge in a dialog broadcast."""
        if not recipient_id:
            return {'success': False, 'error': 'No recipient ID provided.'}

        recipient = request.env['emergency.broadcast.recipient'].sudo().browse(int(recipient_id))
        if not recipient.exists():
            return {'success': False, 'error': 'Recipient record not found.'}

        # Security: only the recipient themselves (or a manager) may acknowledge
        if recipient.user_id.id != request.env.uid:
            if not request.env.user.has_group('emergency_broadcast.group_eb_broadcast_update'):
                return {'success': False, 'error': 'Access denied.'}

        if not recipient.acknowledged:
            recipient.write({
                'acknowledged': True,
                'acknowledged_date': fields.Datetime.now(),
            })
        return {'success': True, 'acknowledged_date': str(recipient.acknowledged_date)}

    @http.route('/emergency_broadcast/get_active_banners', type='jsonrpc', auth='user', methods=['POST'])
    def get_active_banners(self):
        """Return banner data for all active emergency statuses with show_banner=True."""
        banners = request.env['emergency.broadcast.statusbar.config'].get_active_banners()
        return banners

    @http.route('/emergency_broadcast/heartbeat', type='jsonrpc', auth='user', methods=['POST'])
    def heartbeat(self):
        """Frontend calls this every 60 s to mark the user as logged in."""
        request.env['emergency.broadcast.user.presence'].update_presence()
        return {'ok': True}

    @http.route('/emergency_broadcast/trigger_assistance', type='jsonrpc', auth='user', methods=['POST'])
    def trigger_assistance(self):
        """Called when the Emergency Assistance systray button is pressed."""
        broadcast_id = request.env['emergency.broadcast'].create_from_assistance_button()
        return {'success': True, 'broadcast_id': broadcast_id}

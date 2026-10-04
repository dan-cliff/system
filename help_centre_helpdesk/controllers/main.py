import logging

from odoo import http
from odoo.http import request
from odoo.tools import plaintext2html

from odoo.addons.help_centre.controllers.main import HelpCentreController

_logger = logging.getLogger(__name__)


class HelpCentreHelpdeskController(HelpCentreController):

    @http.route('/help/api/create_ticket', type='jsonrpc', auth='public', csrf=False)
    def create_ticket(self, subject, description='', **kwargs):
        """Create a helpdesk ticket from the Help widget.  Requires an authenticated session."""
        if not request.session.uid:
            return {'error': 'auth_required', 'message': 'You must be logged in to lodge a ticket.'}

        if not request.env['res.config.settings']._help_centre_helpdesk_enabled():
            return {'error': 'helpdesk_disabled', 'message': 'Helpdesk integration is not enabled.'}

        if not subject or not subject.strip():
            return {'error': 'subject_required', 'message': 'Please enter a subject for your ticket.'}

        params = request.env['ir.config_parameter'].sudo()
        team_id = int(params.get_param('help_centre.helpdesk_team_id', '0') or '0')
        team = request.env['helpdesk.team'].sudo().browse(team_id).exists()
        user = request.env['res.users'].sudo().browse(request.session.uid)

        vals = {
            'name': subject.strip(),
            'description': plaintext2html(description or ''),
            'partner_id': user.partner_id.id,
        }
        if team:
            vals['team_id'] = team.id

        ticket = request.env['helpdesk.ticket'].sudo().create(vals)
        _logger.info('Help Centre: created helpdesk ticket #%s for user %s', ticket.id, user.name)

        return {
            'ticket_id': ticket.id,
            'ticket_name': ticket.display_name,
        }

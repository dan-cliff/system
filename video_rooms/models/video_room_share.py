# -*- coding: utf-8 -*-
import json
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Wrong share codes allowed from one address before it has to wait.
MAX_FAILURES = 20
FAILURE_WINDOW = timedelta(minutes=15)
OFFER_VALID = timedelta(minutes=10)


class VideoRoomShare(models.Model):
    """Technical: a wireless share from a laptop to a room's screens.

    The laptop opens /video_rooms/share and types the code the room shows. Odoo only
    carries the WebRTC offer and answer between the laptop and the Room Display; the
    picture goes straight across the local network (or through a TURN server set in
    the system parameter video_rooms.ice_servers)."""
    _name = 'video.room.share'
    _description = 'Wireless Share'
    _order = 'id desc'

    room_id = fields.Many2one('video.room', ondelete='cascade', index=True)
    token = fields.Char(required=True, index=True, default=lambda self: secrets.token_urlsafe(24), copy=False)
    # Technical: where the hand-over has got to.
    state = fields.Selection([('waiting', 'Waiting for the Laptop'), ('offered', 'Offered'), ('answered', 'Answered'),
                              ('ended', 'Ended'), ('refused', 'Wrong Code')], default='waiting', required=True)
    offer = fields.Text()
    answer = fields.Text()
    remote_ip = fields.Char()

    @api.model
    def _ice_servers(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('video_rooms.ice_servers') or '[]'
        try:
            servers = json.loads(raw)
            return servers if isinstance(servers, list) else []
        except ValueError:
            return []

    @api.model
    def _start(self, code, ip):
        """A laptop typed ``code``: the share for that room, or UserError."""
        Share = self.sudo()
        since = fields.Datetime.now() - FAILURE_WINDOW
        if Share.search_count([('state', '=', 'refused'), ('remote_ip', '=', ip), ('create_date', '>=', since)]) >= MAX_FAILURES:
            raise UserError(_('Too many wrong codes. Wait a few minutes and try again.'))
        code = ''.join(ch for ch in str(code or '') if ch.isdigit())
        room = self.env['video.room'].sudo().search([('share_code', '=', code)], limit=1) if len(code) == 6 else None
        if not room:
            Share.create({'state': 'refused', 'remote_ip': ip})
            raise UserError(_('That code isn\'t right. Check the code on the room\'s screen.'))
        if not room.display_online:
            raise UserError(_('%s\'s screens aren\'t connected right now.', room.name))
        Share.search([('room_id', '=', room.id), ('state', 'in', ('waiting', 'offered', 'answered'))]).write(
            {'state': 'ended'})
        return Share.create({'room_id': room.id, 'remote_ip': ip})

    def _offer(self, sdp):
        self.ensure_one()
        if self.state != 'waiting':
            raise UserError(_('This share has ended. Start again.'))
        self.write({'offer': sdp, 'state': 'offered'})
        self.room_id._send_command('share', value='wireless', session=self.token)

    def _end(self):
        for share in self.filtered(lambda s: s.state in ('waiting', 'offered', 'answered')):
            share.state = 'ended'
            try:
                share.room_id._send_command('share', value='stop')
            except UserError:
                pass

    @api.autovacuum
    def _gc_shares(self):
        old = fields.Datetime.now() - timedelta(days=1)
        self.sudo().search([('create_date', '<', old)]).unlink()
        stale = fields.Datetime.now() - OFFER_VALID
        self.sudo().search([('state', 'in', ('waiting', 'offered')), ('create_date', '<', stale)]).write({'state': 'ended'})

# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomCallSource(models.Model):
    """Where a call came from (option model under Configuration): an invite email,
    a calendar booking, the Room Console, "Send to Room" from Odoo, ..."""
    _name = 'video.room.call.source'
    _description = 'Video Room Call Source'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class VideoRoomTvControl(models.Model):
    """How a room's TVs are switched on and off (option model under Configuration)."""
    _name = 'video.room.tv.control'
    _description = 'TV Control Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: what the Room Display runs to switch the TV (room_agent.py).
    method = fields.Selection([
        ('none', 'Not Controlled'),
        ('cec', 'HDMI-CEC (cec-client)'),
        ('rs232', 'RS-232 Serial'),
        ('ip', 'LAN (TCP)'),
    ], required=True, default='none')
    on_command = fields.Char(help='RS-232 / LAN: the bytes that switch the TV on, as text with \\x escapes, '
                                  'e.g. "ka 01 01\\r".')
    off_command = fields.Char(help='RS-232 / LAN: the bytes that switch the TV off.')
    note = fields.Text()

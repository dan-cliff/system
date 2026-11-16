# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomCommand(models.Model):
    """Technical queue: Console -> Odoo -> Room Display. The Display collects
    pending commands on each sync (fast poll, DESIGN.md section 7) and reports
    the result."""
    _name = 'video.room.command'
    _description = 'Video Room Command'
    _order = 'id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', index=True)
    command = fields.Selection([
        ('join', 'Join'), ('leave', 'Leave'), ('mic', 'Microphone'), ('camera', 'Camera'),
        ('share', 'Share'), ('layout', 'Layout'), ('volume', 'Volume'), ('tv_power', 'TV Power'),
        ('ptz_preset', 'Camera Preset'), ('restart_browser', 'Restart Browser'), ('self_test', 'Self-Test'),
    ], required=True)
    params = fields.Json()
    state = fields.Selection([('pending', 'Pending'), ('sent', 'Sent'), ('done', 'Done'), ('failed', 'Failed')],
                             default='pending', required=True, index=True)
    result = fields.Char()

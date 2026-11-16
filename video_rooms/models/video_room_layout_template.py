# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomLayoutTemplate(models.Model):
    """A saved Console, Presence or Room Board layout (Configuration), applied to
    many rooms from the Room Designer (DESIGN.md §6e)."""
    _name = 'video.room.layout.template'
    _description = 'Video Room Layout Template'
    _order = 'sequence, name'

    name = fields.Char(required=True, help='e.g. "Standard meeting room".')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: which Room Designer tab the layout belongs to.
    kind = fields.Selection([('console', 'Room Console'), ('presence', 'Presence Screen'), ('board', 'Room Board')],
                            required=True)
    layout = fields.Json(help='Tiles / blocks with their grid positions and options, as saved by the Room Designer.')
    room_count = fields.Integer(compute='_compute_room_count', string='Rooms Using It')

    def _compute_room_count(self):
        Room = self.env['video.room'].sudo()
        for template in self:
            field = 'console_template_id' if template.kind == 'console' else 'presence_template_id'
            template.room_count = Room.search_count([(field, '=', template.id)]) if template.kind != 'board' else 0

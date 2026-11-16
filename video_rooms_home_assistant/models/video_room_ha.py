# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IotNode(models.Model):
    """Home Assistant connection, held on the Room Display Node that reaches it on
    the local network. The token is sent to the Node in its signed sync only."""
    _inherit = 'iot.node'

    ha_url = fields.Char(string='Home Assistant Address',
                         help='As seen from the Node, e.g. http://homeassistant.local:8123')
    ha_token = fields.Char(string='Home Assistant Token', groups='base.group_system', copy=False,
                           help='A long-lived access token of a Home Assistant user made for Video Rooms.')
    ha_status = fields.Char(string='Home Assistant Status', readonly=True, copy=False)


class VideoRoom(models.Model):
    _inherit = 'video.room'

    ha_control_ids = fields.One2many('video.room.ha.control', 'room_id', string='Room Controls')
    ha_preset_ids = fields.One2many('video.room.ha.preset', 'room_id', string='Room Presets')
    ha_publish_state = fields.Boolean(
        string='Publish Room State to Home Assistant', default=True,
        help='Keeps sensor.video_room_<room> (available / in use / in call / do not disturb) up to date.')


class VideoRoomHaControl(models.Model):
    """One Home Assistant entity in a room, shown on the Room Console. The kind of
    control comes from the entity's domain: light, switch (e.g. privacy film),
    climate (A/C), cover (blinds), fan, scene, script."""
    _name = 'video.room.ha.control'
    _description = 'Video Room Control (Home Assistant)'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='Shown on the Console, e.g. "Ceiling Lights", "Privacy Glass".')
    entity_id = fields.Char(string='Entity', required=True, help='e.g. light.boardroom_ceiling')
    domain = fields.Char(compute='_compute_domain', store=True)
    on_presence = fields.Boolean(string='Show State at the Door',
                                 help='e.g. room temperature on the Presence screen.')

    @api.depends('entity_id')
    def _compute_domain(self):
        for control in self:
            control.domain = (control.entity_id or '').partition('.')[0]


class VideoRoomHaPreset(models.Model):
    """A one-tap room setting: several controls at once."""
    _name = 'video.room.ha.preset'
    _description = 'Video Room Preset (Home Assistant)'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='e.g. "Meeting", "Presentation", "Room Off".')
    line_ids = fields.One2many('video.room.ha.preset.line', 'preset_id')
    # TODO(build): triggers as a Many2many to an option model (call starts / call ends / booking starts
    #              (with lead minutes, e.g. pre-cool) / booking ends / Do Not Disturb on / off).


class VideoRoomHaPresetLine(models.Model):
    _name = 'video.room.ha.preset.line'
    _description = 'Video Room Preset Step'
    _order = 'preset_id, sequence, id'

    preset_id = fields.Many2one('video.room.ha.preset', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    control_id = fields.Many2one('video.room.ha.control', required=True, ondelete='cascade')
    service = fields.Char(required=True, help='Home Assistant action, e.g. turn_on, set_cover_position.')
    service_data = fields.Json(help='e.g. {"brightness_pct": 30} or {"position": 0}.')

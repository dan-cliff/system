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

    ha_area = fields.Char(string='Home Assistant Area',
                          help='The room\'s Area in Home Assistant, used by Discover Devices.')
    ha_control_ids = fields.One2many('video.room.ha.control', 'room_id', string='Room Controls')
    ha_category_ids = fields.Many2many('video.room.ha.category', compute='_compute_ha_category_ids',
                                       string='Devices in the Room',
                                       help='The kinds of device the room has; the Console only shows these panels.')
    ha_preset_ids = fields.One2many('video.room.ha.preset', 'room_id', string='Room Presets')
    @api.depends('ha_control_ids.category_id')
    def _compute_ha_category_ids(self):
        for room in self:
            room.ha_category_ids = room.ha_control_ids.category_id

    def action_ha_discover(self):
        """Ask the Display Node for the entities in the room's Home Assistant Area and suggest a
        Room Control for each, with its likely category, to confirm or untick."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    ha_publish_state = fields.Boolean(
        string='Publish Room State to Home Assistant', default=True,
        help='Keeps sensor.video_room_<room> (available / in use / in call / do not disturb) up to date.')


class VideoRoomHaCategory(models.Model):
    """A kind of room device (option model under Configuration): Lighting, Air
    Conditioning, Blinds, Smart Window Film, Scenes, ... New kinds are new records."""
    _name = 'video.room.ha.category'
    _description = 'Room Device Category (Home Assistant)'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    entity_domains = fields.Char(required=True, help='Home Assistant domains it covers, e.g. "light,switch".')
    # Technical: which Console panel draws it.
    panel = fields.Selection([('lighting', 'Lights'), ('climate', 'Climate'), ('cover', 'Blinds / Covers'),
                              ('glass', 'Clear / Frosted'), ('scene', 'Run')], required=True)


class VideoRoomHaControl(models.Model):
    """One Home Assistant entity in a room, in one of the room's device categories,
    shown on the Room Console in that category's panel."""
    _name = 'video.room.ha.control'
    _description = 'Video Room Control (Home Assistant)'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='Shown on the Console, e.g. "Ceiling Lights", "Privacy Glass".')
    category_id = fields.Many2one('video.room.ha.category', string='Category', required=True)
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

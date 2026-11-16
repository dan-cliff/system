# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ADMIN = 'video_rooms.group_video_rooms_admin'
ENTITY_RE = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')
# How the Console controls each kind of entity: (on service, off service).
ON_OFF = {
    'light': ('turn_on', 'turn_off'), 'switch': ('turn_on', 'turn_off'), 'fan': ('turn_on', 'turn_off'),
    'cover': ('open_cover', 'close_cover'), 'scene': ('turn_on', 'turn_on'), 'script': ('turn_on', 'turn_on'),
    'climate': ('turn_on', 'turn_off'), 'input_boolean': ('turn_on', 'turn_off'),
}


class IotNode(models.Model):
    """The Home Assistant connection, kept on the Room Display Node that reaches it on
    the local network. Odoo never connects to Home Assistant: the token is handed to
    the Node in its signed sync, and the Node calls Home Assistant."""
    _inherit = 'iot.node'

    ha_url = fields.Char(string='Home Assistant Address',
                         help='As seen from the room PC, e.g. http://homeassistant.local:8123')
    ha_token = fields.Char(string='Home Assistant Token', groups='base.group_system', copy=False,
                           help='A long-lived access token of a Home Assistant user made for Video Rooms '
                                '(Home Assistant › your profile › Security › Long-lived access tokens).')
    ha_states = fields.Json(string='Home Assistant States', readonly=True, copy=False,
                            help='The states of the room\'s devices, as the Display last read them.')
    ha_status = fields.Char(string='Home Assistant Status', readonly=True, copy=False)
    ha_discovered = fields.Json(readonly=True, copy=False)


class VideoRoomHaCategory(models.Model):
    """A kind of room device (option model under Configuration): Lighting, Air
    Conditioning, Blinds, Smart Window Film, Scenes... New kinds are new records."""
    _name = 'video.room.ha.category'
    _description = 'Room Device Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    entity_domains = fields.Char(string='Home Assistant Domains', required=True,
                                 help='The Home Assistant entity domains it covers, e.g. "light,switch".')
    # Technical: which Console tile draws it.
    panel = fields.Selection([('lighting', 'Lighting'), ('climate', 'Air Conditioning'), ('cover', 'Blinds'),
                              ('glass', 'Window Film'), ('scene', 'Room Presets')], required=True)

    def _domains(self):
        self.ensure_one()
        return [d.strip() for d in (self.entity_domains or '').split(',') if d.strip()]


class VideoRoomHaTrigger(models.Model):
    """When a room preset runs by itself (option model under Configuration)."""
    _name = 'video.room.ha.trigger'
    _description = 'Room Preset Trigger'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: the event code listens for.
    event = fields.Selection([('call_start', 'Call Starts'), ('call_end', 'Call Ends'),
                              ('booking_start', 'Booking Starts'), ('booking_end', 'Booking Ends'),
                              ('dnd_on', 'Do Not Disturb On'), ('dnd_off', 'Do Not Disturb Off')], required=True)


class VideoRoomHaControl(models.Model):
    """One Home Assistant entity in a room, in one of the room's device categories."""
    _name = 'video.room.ha.control'
    _description = 'Room Control'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True,
                            help='Discover Devices adds what it finds as archived suggestions: tick to use one.')
    name = fields.Char(required=True, help='Shown on the Console, e.g. "Ceiling Lights", "Glass Wall".')
    category_id = fields.Many2one('video.room.ha.category', string='Category', required=True)
    entity_id = fields.Char(string='Entity', required=True, help='e.g. light.boardroom_ceiling')
    domain = fields.Char(compute='_compute_domain', store=True)
    on_presence = fields.Boolean(string='Show at the Door', help='e.g. the room temperature on the door screen.')

    @api.depends('entity_id')
    def _compute_domain(self):
        for control in self:
            control.domain = (control.entity_id or '').partition('.')[0]

    @api.constrains('entity_id', 'category_id')
    def _check_entity(self):
        for control in self:
            if not ENTITY_RE.match(control.entity_id or ''):
                raise ValidationError(_('"%s" isn\'t a Home Assistant entity (e.g. light.boardroom_ceiling).',
                                        control.entity_id))
            if control.domain not in control.category_id._domains():
                raise ValidationError(_('%(entity)s isn\'t a %(category)s device (%(domains)s).',
                                        entity=control.entity_id, category=control.category_id.name,
                                        domains=control.category_id.entity_domains))

    def _service_call(self, value):
        """(domain, service, data) to set this control to ``value`` (bool, or a number)."""
        self.ensure_one()
        data = {'entity_id': self.entity_id}
        domain = self.domain
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if domain == 'light':
                return domain, 'turn_on', dict(data, brightness_pct=max(0, min(100, int(value))))
            if domain == 'cover':
                return domain, 'set_cover_position', dict(data, position=max(0, min(100, int(value))))
            if domain == 'climate':
                return domain, 'set_temperature', dict(data, temperature=float(value))
        on, off = ON_OFF.get(domain, ('turn_on', 'turn_off'))
        return domain, on if value else off, data


class VideoRoomHaPreset(models.Model):
    """A one-tap room setting: several controls at once, optionally run by a trigger."""
    _name = 'video.room.ha.preset'
    _description = 'Room Preset'
    _order = 'room_id, sequence, id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, help='e.g. "Meeting", "Presentation", "Room Off".')
    line_ids = fields.One2many('video.room.ha.preset.line', 'preset_id', string='Steps', copy=True)
    trigger_ids = fields.Many2many('video.room.ha.trigger', string='Run Automatically When')
    lead_minutes = fields.Integer(string='Minutes Before a Booking',
                                  help='With "Booking Starts": run this many minutes early, e.g. to pre-cool the room.')
    last_run_key = fields.Char(readonly=True, copy=False)

    def action_run(self):
        for preset in self:
            preset.room_id._ha_check()
            for line in preset.line_ids:
                preset.room_id._ha_send(*line.control_id._service_call(line._value()))
        return True


class VideoRoomHaPresetLine(models.Model):
    _name = 'video.room.ha.preset.line'
    _description = 'Room Preset Step'
    _order = 'preset_id, sequence, id'

    preset_id = fields.Many2one('video.room.ha.preset', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    control_id = fields.Many2one('video.room.ha.control', required=True, ondelete='cascade',
                                 domain="[('room_id', '=', parent.room_id)]")
    # Technical: how the step sets the control.
    action = fields.Selection([('on', 'On / Open / Frosted'), ('off', 'Off / Close / Clear'), ('level', 'Set to')],
                              required=True, default='on')
    level = fields.Float(help='Brightness %, blind position % or temperature °C.')

    def _value(self):
        self.ensure_one()
        return self.level if self.action == 'level' else self.action == 'on'


class VideoRoom(models.Model):
    _inherit = 'video.room'

    ha_area = fields.Char(string='Home Assistant Area',
                          help="The room's Area in Home Assistant, used by Discover Devices.")
    ha_control_ids = fields.One2many('video.room.ha.control', 'room_id', string='Room Controls',
                                     context={'active_test': False})
    ha_preset_ids = fields.One2many('video.room.ha.preset', 'room_id', string='Room Presets')
    ha_category_ids = fields.Many2many('video.room.ha.category', compute='_compute_ha_category_ids',
                                       string='Devices in the Room',
                                       help='The kinds of device the room has; the Console only shows these.')
    ha_publish_state = fields.Boolean(
        string='Publish Room Status to Home Assistant', default=True,
        help='Keeps sensor.video_room_<room> (available / booked soon / in use / do not disturb) up to date '
             'for Home Assistant automations.')

    @api.depends('ha_control_ids.category_id', 'ha_control_ids.active')
    def _compute_ha_category_ids(self):
        for room in self:
            room.ha_category_ids = room.ha_control_ids.filtered('active').category_id

    # ── Talking to Home Assistant (through the Room Display) ─────────────
    def _ha_connection(self):
        self.ensure_one()
        node = self.sudo().display_node_id
        if not node or not node.ha_url or not node.ha_token:
            return None
        return {'url': node.ha_url.rstrip('/'), 'token': node.ha_token}

    def _ha_check(self):
        if not self._ha_connection():
            raise UserError(_('Connect %s\'s Room Display to Home Assistant first (its Home Assistant tab).',
                              self.name))

    def _ha_send(self, domain, service, data):
        connection = self._ha_connection()
        return self._send_command('device', kind='ha', url=connection['url'], token=connection['token'],
                                  domain=domain, service=service, data=data)

    def _ha_run_trigger(self, event, key=None):
        """Run the room's presets for ``event`` (once per ``key`` when given)."""
        for room in self.sudo():
            if not room._ha_connection():
                continue
            presets = room.ha_preset_ids.filtered(lambda p: event in p.trigger_ids.mapped('event'))
            for preset in presets:
                run_key = '%s:%s' % (event, key) if key else False
                if run_key and preset.last_run_key == run_key:
                    continue
                preset.action_run()
                if run_key:
                    preset.last_run_key = run_key

    def action_ha_discover(self):
        """Ask the Room Display which entities are in the room's Home Assistant Area;
        they are added as archived suggestions to tick."""
        self.ensure_one()
        self._check_design()
        if not self.ha_area:
            raise UserError(_('Set the room\'s Home Assistant Area first.'))
        self._ha_check()
        connection = self._ha_connection()
        self._send_command('device', kind='ha_discover', url=connection['url'], token=connection['token'],
                           area=self.ha_area)
        return self._notify(_('Looking for devices in the "%s" area: they appear under Room Controls within a '
                              'few seconds (reload the page).', self.ha_area))

    def _ha_adopt_discovered(self, entities):
        """Add discovered entities as archived suggestions (with their likely category)."""
        self.ensure_one()
        categories = self.env['video.room.ha.category'].sudo().search([])
        known = set(self.sudo().with_context(active_test=False).ha_control_ids.mapped('entity_id'))
        Control = self.env['video.room.ha.control'].sudo()
        for item in entities or []:
            entity = str(item.get('entity_id') if isinstance(item, dict) else item)
            if entity in known or not ENTITY_RE.match(entity):
                continue
            domain = entity.partition('.')[0]
            name = (item.get('name') if isinstance(item, dict) else None) or entity.partition('.')[2].replace('_', ' ').title()
            glass = re.search(r'glass|film|privacy|window', entity)
            category = next((c for c in categories if c.panel == 'glass' and glass and domain in c._domains()), None) \
                or next((c for c in categories if domain in c._domains() and c.panel != 'glass'), None)
            if category:
                Control.create({'room_id': self.id, 'name': name, 'entity_id': entity, 'category_id': category.id,
                                'active': False})

    # ── Console ──────────────────────────────────────────────────────────
    def _console_controls(self):
        controls = super()._console_controls()
        room = self.sudo()
        if not room._ha_connection():
            return controls
        states = room.display_node_id.ha_states or {}
        for control in room.ha_control_ids.filtered('active'):
            state = (states.get(control.entity_id) or {}).get('state')
            controls.append({'id': control.id, 'name': control.name, 'label': control.name,
                             'panel': control.category_id.panel, 'entity': control.entity_id,
                             'on': state in ('on', 'open', 'heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only'),
                             'state': state or ''})
        for preset in room.ha_preset_ids:
            controls.append({'id': 'preset-%s' % preset.id, 'name': preset.name, 'label': preset.name,
                             'panel': 'scene', 'on': False, 'state': ''})
        return controls

    def _console_device(self, params):
        room = self.sudo()
        control_id = params.get('control_id')
        if isinstance(control_id, str) and control_id.startswith('preset-'):
            preset = room.ha_preset_ids.filtered(lambda p: p.id == int(control_id.split('-')[1]))
            if not preset:
                raise UserError(_('That preset isn\'t in this room.'))
            preset.action_run()
            return _('%s set.', preset.name)
        if params.get('kind'):
            return super()._console_device(params)
        control = room.ha_control_ids.filtered(lambda c: c.id == int(control_id or 0) and c.active)
        if not control:
            raise UserError(_('That control isn\'t in this room.'))
        room._ha_check()
        room._ha_send(*control._service_call(params.get('value')))
        return ''

    def _presence_payload(self):
        payload = super()._presence_payload()
        room = self.sudo()
        states = room.display_node_id.ha_states or {}
        for control in room.ha_control_ids.filtered(lambda c: c.active and c.on_presence):
            attributes = (states.get(control.entity_id) or {}).get('attributes') or {}
            temperature = attributes.get('current_temperature')
            if temperature is not None:
                payload['temperature'] = '%s °C' % temperature
                break
        return payload

    # ── Room Display sync ────────────────────────────────────────────────
    def _display_sync_payload(self):
        payload = super()._display_sync_payload()
        room = self.sudo()
        connection = room._ha_connection()
        if connection:
            payload['ha'] = dict(connection,
                                 entities=room.ha_control_ids.filtered('active').mapped('entity_id'),
                                 sensor='sensor.video_room_%s' % re.sub(r'[^a-z0-9]+', '_', room.name.lower()).strip('_'),
                                 publish=room.ha_publish_state)
        return payload

    def _display_reported(self, state):
        super()._display_reported(state)
        node = self.sudo().display_node_id
        vals = {}
        if 'ha_states' in state and state['ha_states'] != node.ha_states:
            vals['ha_states'] = state['ha_states']
        if state.get('ha_status') and state['ha_status'] != node.ha_status:
            vals['ha_status'] = str(state['ha_status'])[:120]
        if vals:
            node.write(vals)
        discovered = state.get('ha_discovered')
        if isinstance(discovered, dict) and discovered.get('area') == self.ha_area:
            self._ha_adopt_discovered(discovered.get('entities'))

    # ── Triggers ─────────────────────────────────────────────────────────
    def action_set_dnd(self, active=True, minutes=None, message=None, auto=False):
        was = {room.id: room.dnd_active for room in self}
        result = super().action_set_dnd(active, minutes, message, auto)
        for room in self:
            if bool(active) != was.get(room.id):
                room._ha_run_trigger('dnd_on' if active else 'dnd_off')
        return result

    @api.model
    def _cron_housekeeping(self):
        super()._cron_housekeeping()
        now = fields.Datetime.now()
        for preset in self.env['video.room.ha.preset'].sudo().search([('trigger_ids.event', 'in', ('booking_start', 'booking_end'))]):
            room = preset.room_id
            events = set(preset.trigger_ids.mapped('event'))
            window_start = now - timedelta(minutes=2)
            if 'booking_start' in events:
                lead = timedelta(minutes=preset.lead_minutes or 0)
                for meeting in room._bookings(now, now + lead + timedelta(minutes=1)):
                    if window_start <= meeting.date_start - lead <= now:
                        room._ha_run_trigger('booking_start', key=meeting.id)
            if 'booking_end' in events:
                for meeting in room._bookings(now - timedelta(hours=12), now + timedelta(minutes=1)):
                    end = room._meeting_end(meeting)
                    if window_start <= end <= now:
                        room._ha_run_trigger('booking_end', key=meeting.id)


class VideoRoomCall(models.Model):
    _inherit = 'video.room.call'

    def _report_state(self, state, error=None):
        before = {call.id: call.state for call in self}
        result = super()._report_state(state, error)
        for call in self:
            if before.get(call.id) != 'in_call' and call.state == 'in_call':
                call.room_id._ha_run_trigger('call_start', key=call.id)
            elif before.get(call.id) not in ('done', 'failed') and call.state in ('done', 'failed'):
                call.room_id._ha_run_trigger('call_end', key=call.id)
        return result

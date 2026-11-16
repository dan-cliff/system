# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHomeAssistant(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.display = cls.env['iot.node'].create({
            'name': 'Display', 'role': 'video_rooms_display',
            'ha_url': 'http://homeassistant.local:8123/', 'ha_token': 'secret-token'})
        cls.room = cls.env['video.room'].create({'name': 'Board Room', 'display_node_id': cls.display.id,
                                                 'ha_area': 'Board Room'})
        cls.lighting = cls.env.ref('video_rooms_home_assistant.ha_category_lighting')
        cls.film = cls.env.ref('video_rooms_home_assistant.ha_category_window_film')
        cls.Control = cls.env['video.room.ha.control']
        cls.lights = cls.Control.create({'room_id': cls.room.id, 'name': 'Ceiling', 'category_id': cls.lighting.id,
                                         'entity_id': 'light.board_room_ceiling'})
        cls.glass = cls.Control.create({'room_id': cls.room.id, 'name': 'Glass wall', 'category_id': cls.film.id,
                                        'entity_id': 'switch.board_room_privacy_film'})

    def _commands(self):
        return self.env['video.room.command'].search([('room_id', '=', self.room.id)], order='id')

    def test_rooms_show_only_their_devices(self):
        self.assertEqual(set(self.room.ha_category_ids.mapped('panel')), {'lighting', 'glass'})
        panels = {c['panel'] for c in self.room._console_controls()}
        self.assertEqual(panels, {'lighting', 'glass'})
        with self.assertRaises(ValidationError):
            self.Control.create({'room_id': self.room.id, 'name': 'Wrong', 'category_id': self.lighting.id,
                                 'entity_id': 'cover.board_room_blinds'})

    def test_console_device_goes_through_the_display(self):
        self.room._console_device({'control_id': self.lights.id, 'value': True})
        command = self._commands()[-1]
        self.assertEqual(command.command, 'device')
        self.assertEqual((command.params['domain'], command.params['service']), ('light', 'turn_on'))
        self.assertEqual(command.params['url'], 'http://homeassistant.local:8123')
        self.room._console_device({'control_id': self.lights.id, 'value': 30})
        self.assertEqual(self._commands()[-1].params['data']['brightness_pct'], 30)
        payload = self.room._display_sync_payload()
        self.assertEqual(payload['ha']['sensor'], 'sensor.video_room_board_room')
        self.assertIn('light.board_room_ceiling', payload['ha']['entities'])
        self.assertNotIn('ha', self.room._display_payload(), 'the idle page never gets the token')

    def test_preset_runs_on_do_not_disturb(self):
        preset = self.env['video.room.ha.preset'].create({
            'room_id': self.room.id, 'name': 'Privacy',
            'trigger_ids': [(6, 0, [self.env.ref('video_rooms_home_assistant.ha_trigger_dnd_on').id])],
            'line_ids': [(0, 0, {'control_id': self.glass.id, 'action': 'on'})],
        })
        self.room.action_set_dnd(True)
        command = self._commands()[-1]
        self.assertEqual(command.params['data']['entity_id'], 'switch.board_room_privacy_film')
        self.assertTrue(preset)
        # Presets show on the Console too.
        self.assertIn('Privacy', [c['name'] for c in self.room._console_controls()])

    def test_discover_devices(self):
        self.room._display_reported({'ha_discovered': {'area': 'Board Room', 'entities': [
            {'entity_id': 'climate.board_room_ac', 'name': 'Board Room AC'},
            {'entity_id': 'cover.board_room_blinds', 'name': None},
            {'entity_id': 'light.board_room_ceiling', 'name': 'Already there'},
        ]}})
        found = self.Control.with_context(active_test=False).search([('room_id', '=', self.room.id), ('active', '=', False)])
        self.assertEqual(sorted(found.mapped('entity_id')), ['climate.board_room_ac', 'cover.board_room_blinds'])
        self.assertEqual(found.filtered(lambda c: c.domain == 'cover').category_id.panel, 'cover')

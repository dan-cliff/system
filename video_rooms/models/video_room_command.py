# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

# A command not collected by the Display in this time is dropped (the room moved on).
COMMAND_EXPIRY = timedelta(minutes=2)


class VideoRoomCommand(models.Model):
    """Technical queue: Console / Odoo -> Room Display. The Display collects pending
    commands on each sync (about every second during a call) and reports results."""
    _name = 'video.room.command'
    _description = 'Video Room Command'
    _order = 'id'

    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', index=True)
    call_id = fields.Many2one('video.room.call', ondelete='set null')
    command = fields.Selection([
        ('join', 'Join'), ('leave', 'Leave'), ('mic', 'Microphone'), ('camera', 'Camera'),
        ('share', 'Share'), ('layout', 'Layout'), ('volume', 'Volume'), ('tv_power', 'TV Power'),
        ('ptz_preset', 'Camera Preset'), ('identify', 'Identify Screens'), ('restart_browser', 'Restart Browser'),
        ('self_test', 'Self-Test'), ('admit_share', 'Wireless Share'), ('device', 'Room Device'),
    ], required=True)
    params = fields.Json()
    state = fields.Selection([('pending', 'Pending'), ('sent', 'Sent'), ('done', 'Done'), ('failed', 'Failed'),
                              ('expired', 'Expired')], default='pending', required=True, index=True)
    result = fields.Char()
    sent_at = fields.Datetime()
    done_at = fields.Datetime()

    def _collect(self, room):
        """Pending commands for the room's Display (marked sent); stale ones expire."""
        now = fields.Datetime.now()
        pending = self.sudo().search([('room_id', '=', room.id), ('state', '=', 'pending')])
        stale = pending.filtered(lambda c: c.create_date < now - COMMAND_EXPIRY)
        stale.write({'state': 'expired'})
        fresh = pending - stale
        fresh.write({'state': 'sent', 'sent_at': now})
        return [{'id': c.id, 'command': c.command, 'params': c.params or {}} for c in fresh]

    @api.model
    def _report(self, room, results):
        now = fields.Datetime.now()
        for item in results or []:
            if not isinstance(item, dict):
                continue
            command = self.sudo().search([('id', '=', int(item.get('id') or 0)), ('room_id', '=', room.id)])
            if command and command.state in ('pending', 'sent'):
                command.write({'state': 'done' if item.get('ok') else 'failed',
                               'result': str(item.get('message') or '')[:250] or False, 'done_at': now})

    @api.autovacuum
    def _gc_commands(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

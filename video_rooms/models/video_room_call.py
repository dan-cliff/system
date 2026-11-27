# -*- coding: utf-8 -*-
from odoo import api, fields, models

ADMIN = 'video_rooms.group_video_rooms_admin'


class VideoRoomCall(models.Model):
    """Each time a room joins (or tries to join) a call: the call history.
    Kept (decided, DESIGN.md §11)."""
    _name = 'video.room.call'
    _description = 'Video Room Call'
    _inherit = ['mail.thread']
    _order = 'id desc'
    # Calls inherit their room's Organisation units (org_structure).
    _org_parent_field = 'room_id'

    name = fields.Char(required=True, tracking=True)
    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', tracking=True, index=True)
    company_id = fields.Many2one('res.company', related='room_id.company_id', store=True, readonly=True)
    meeting_id = fields.Many2one('meeting.meeting', string='Booking', ondelete='set null', index=True)
    url = fields.Char(string='Meeting Link', groups=ADMIN, help='Only Video Rooms administrators see it.')
    platform_id = fields.Many2one('video.room.platform', string='Platform')
    source_id = fields.Many2one('video.room.call.source', string='Source')
    organiser_partner_id = fields.Many2one('res.partner', string='Organiser',
                                           help='Who invited the room. Remapped to Advanced Accounts by the '
                                                'optional advanced_accounts_video_rooms app.')
    joined_at = fields.Datetime(string='Joined', readonly=True)
    left_at = fields.Datetime(string='Left', readonly=True)
    duration = fields.Float(string='Duration (minutes)', compute='_compute_duration', store=True)
    # Technical: the state the Room Display reports.
    state = fields.Selection([
        ('joining', 'Joining'), ('lobby', 'In Lobby'), ('in_call', 'In Call'),
        ('done', 'Ended'), ('failed', 'Could Not Join'),
    ], default='joining', required=True, tracking=True)
    failure_reason = fields.Char(readonly=True, tracking=True)

    @api.depends('joined_at', 'left_at')
    def _compute_duration(self):
        for call in self:
            call.duration = ((call.left_at - call.joined_at).total_seconds() / 60
                             if call.joined_at and call.left_at else 0)

    def _report_state(self, state, error=None):
        """The Room Display reports how the call is going."""
        mapping = {'prejoin': 'joining', 'joining': 'joining', 'lobby': 'lobby', 'in_call': 'in_call',
                   'ended': 'done', 'idle': 'done', 'error': 'failed'}
        now = fields.Datetime.now()
        for call in self.sudo():
            new = mapping.get(state)
            if not new or call.state in ('done', 'failed') or new == call.state:
                continue
            vals = {'state': new}
            if new == 'in_call' and not call.joined_at:
                vals['joined_at'] = now
            if new in ('done', 'failed'):
                vals['left_at'] = now
                if new == 'failed':
                    vals['failure_reason'] = (error or '')[:250] or False
                if call.room_id.dnd_auto:
                    call.room_id.action_set_dnd(False)
            call.write(vals)

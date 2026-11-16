# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VideoRoomCall(models.Model):
    """One meeting for a room: the schedule (planned) and the history (joined,
    left, outcome). Primary model."""
    _name = 'video.room.call'
    _description = 'Video Room Call'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True, tracking=True)
    room_id = fields.Many2one('video.room', required=True, ondelete='cascade', tracking=True)
    company_id = fields.Many2one(related='room_id.company_id', store=True)
    meeting_id = fields.Many2one('meeting.meeting', string='Booking', ondelete='set null', index=True)
    url = fields.Char(string='Meeting Link', required=True)
    platform_id = fields.Many2one('video.room.platform', compute='_compute_platform_id', store=True,
                                  readonly=False)
    date_start = fields.Datetime(string='Starts')
    date_end = fields.Datetime(string='Ends')
    organiser_partner_id = fields.Many2one('res.partner', string='Organiser',
                                           help='Who invited the room (from the invite). Remapped to Advanced '
                                                'Accounts by the optional advanced_accounts_video_rooms app.')
    # TODO(build): source_id -> video.room.call.source (option model: invite email / calendar / console /
    #              sent from Odoo), joined_at, left_at; _org_parent_field = 'room_id' (DESIGN.md §13).
    # Technical: workflow state the Display reports.
    state = fields.Selection([
        ('planned', 'Planned'), ('joining', 'Joining'), ('lobby', 'In Lobby'), ('in_call', 'In Call'),
        ('done', 'Ended'), ('failed', 'Could Not Join'), ('cancelled', 'Cancelled'),
    ], default='planned', required=True, tracking=True)
    failure_reason = fields.Char(readonly=True)

    @api.depends('url')
    def _compute_platform_id(self):
        Platform = self.env['video.room.platform']
        for call in self:
            call.platform_id = Platform._detect(call.url)

    def action_join(self):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomBoard(models.Model):
    """A Room Board: the live status of several rooms at once, in Odoo (Overview) and
    on wall screens (DESIGN.md §6f). Primary model."""
    _name = 'video.room.board'
    _description = 'Room Board'
    _order = 'name'

    name = fields.Char(required=True, help='e.g. "Head Office - Meeting Rooms".')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    # Technical: how rooms are chosen.
    room_selection = fields.Selection([('manual', 'Chosen Rooms'), ('rule', 'Rooms Matching a Rule')],
                                      required=True, default='manual')
    room_ids = fields.Many2many('video.room', string='Rooms')
    room_domain = fields.Char(string='Rule', default='[]',
                              help='e.g. every room in a Location; rooms added later appear by themselves.')
    # Technical: the board's view, used by the OWL component.
    view_mode = fields.Selection([('tiles', 'Tiles'), ('list', 'List'), ('timeline', 'Timeline'),
                                  ('tiles_timeline', 'Tiles + Timeline')], required=True, default='tiles_timeline')
    columns = fields.Integer(default=4)
    sort_by = fields.Selection([('name', 'Name'), ('availability', 'Availability'), ('next', 'Next Booking')],
                               default='name', required=True)
    show_next_booking = fields.Boolean(default=True)
    show_platform = fields.Boolean(string='Show Call Platform', default=True)
    show_capacity = fields.Boolean(default=False)
    show_temperature = fields.Boolean(default=False, help='Needs Home Assistant.')
    allow_book_now = fields.Boolean(string='Book Now on Touchscreens', default=False)
    layout_template_id = fields.Many2one('video.room.layout.template', domain="[('kind', '=', 'board')]")
    style = fields.Json(help='Colours, logo, light/dark, as set in the designer.')
    # Existing PCs / Android tablets showing this board, each a browser Node (DESIGN.md §7).
    screen_node_ids = fields.Many2many('iot.node', string='Board Screens',
                                       domain="[('role', 'in', ('video_rooms_board',))]")

    def _get_rooms(self):
        """The rooms the board shows: chosen ones, or those matching the rule."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

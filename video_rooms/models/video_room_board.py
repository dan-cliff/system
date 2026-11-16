# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval


class VideoRoomBoard(models.Model):
    """A Room Board: the live status of several rooms at once, in Odoo (Overview) and
    full screen on existing PCs and Android tablets (DESIGN.md §6f)."""
    _name = 'video.room.board'
    _description = 'Room Board'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True, help='e.g. "Head Office - Meeting Rooms".')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    # Technical: how rooms are chosen.
    room_selection = fields.Selection([('manual', 'Chosen Rooms'), ('rule', 'Rooms Matching a Rule')],
                                      string='Rooms Shown', required=True, default='manual')
    room_ids = fields.Many2many('video.room', string='Rooms')
    room_domain = fields.Char(string='Rule', default='[]',
                              help='Which rooms to show, e.g. every room in a Location. Rooms added later '
                                   'appear by themselves.')
    # Technical: the board's view, used by the board pages.
    view_mode = fields.Selection([('tiles_timeline', 'Tiles + Timeline'), ('tiles', 'Tiles'),
                                  ('timeline', 'Timeline'), ('list', 'List')], string='View', required=True,
                                 default='tiles_timeline')
    columns = fields.Integer(default=4)
    sort_by = fields.Selection([('name', 'Name'), ('availability', 'Availability'), ('next', 'Next Booking')],
                               default='name', required=True)
    show_current = fields.Boolean(string='Show Current Booking', default=True)
    show_next_booking = fields.Boolean(default=True)
    show_platform = fields.Boolean(string='Show Call Platform', default=True)
    show_dnd = fields.Boolean(string='Show Do Not Disturb', default=True)
    show_capacity = fields.Boolean(default=False)
    allow_book_now = fields.Boolean(string='Book Now on Touchscreens', default=False,
                                    help='Let touchscreen boards book a free room from its tile.')
    theme = fields.Selection([('dark', 'Dark'), ('light', 'Light')], default='dark', required=True)
    screen_node_ids = fields.One2many('iot.node', 'video_room_board_id', string='Board Screens')
    room_count = fields.Integer(compute='_compute_room_count')

    @api.constrains('columns')
    def _check_columns(self):
        if any(not 1 <= board.columns <= 8 for board in self):
            raise ValidationError(_('A board shows 1 to 8 columns.'))

    @api.depends('room_ids', 'room_domain', 'room_selection')
    def _compute_room_count(self):
        for board in self:
            board.room_count = len(board._get_rooms())

    def _get_rooms(self):
        """The rooms the board shows: chosen ones, or those matching the rule (sudo)."""
        self.ensure_one()
        Room = self.env['video.room'].sudo()
        if self.room_selection == 'manual':
            rooms = self.sudo().room_ids
        else:
            try:
                domain = safe_eval(self.room_domain or '[]')
            except Exception:
                domain = []
            rooms = Room.search(domain + [('company_id', '=', self.company_id.id)])
        return rooms.filtered('active')

    def _payload(self):
        self.ensure_one()
        board = self.sudo()
        rooms = [room._status_payload() for room in board._get_rooms()]
        order = {'dnd': 0, 'in_use': 1, 'soon': 2, 'available': 3}
        if board.sort_by == 'availability':
            rooms.sort(key=lambda r: (order.get(r['availability'], 9), r['name']))
        elif board.sort_by == 'next':
            rooms.sort(key=lambda r: ((r['next'] or {}).get('start_ts') or '9999', r['name']))
        else:
            rooms.sort(key=lambda r: r['name'].lower())
        first = rooms[0] if rooms else {}
        return {
            'id': board.id, 'name': board.name, 'view': board.view_mode, 'columns': board.columns,
            'theme': board.theme, 'book_now': board.allow_book_now,
            'show': {'current': board.show_current, 'next': board.show_next_booking,
                     'platform': board.show_platform, 'dnd': board.show_dnd, 'capacity': board.show_capacity},
            'now': first.get('now', ''), 'date': first.get('date', ''),
            'rooms': rooms,
        }

    @api.model
    def get_overview(self, board_id=None):
        """The Overview dashboard in Odoo: the user's boards, and the chosen board's
        status (or every room the user can see when no board is chosen)."""
        boards = self.search([])
        board = boards.filtered(lambda b: b.id == int(board_id or 0))[:1] if board_id else self.browse()
        if board:
            payload = board._payload()
        else:
            rooms = self.env['video.room'].search([])
            statuses = sorted((room._status_payload() for room in rooms), key=lambda r: r['name'].lower())
            first = statuses[0] if statuses else {}
            payload = {
                'id': False, 'name': _('All Rooms'), 'view': 'tiles_timeline', 'columns': 4, 'theme': 'dark',
                'book_now': False, 'now': first.get('now', ''), 'date': first.get('date', ''),
                'show': {'current': True, 'next': True, 'platform': True, 'dnd': True, 'capacity': True},
                'rooms': statuses,
            }
        return {'boards': [{'id': b.id, 'name': b.name} for b in boards], 'board': payload}

    def action_add_board_screen(self):
        self.ensure_one()
        if not self.env.user.has_group('video_rooms.group_video_rooms_admin'):
            raise UserError(_('Only Video Rooms administrators can add board screens.'))
        node = self.env['iot.node']._video_rooms_create_browser_node(
            'video_rooms_board', '%s - %s' % (self.name, _('Screen')), board=self)
        return node.action_pair()

    def action_open_board(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'video_rooms.room_board', 'name': self.name,
                'params': {'board_id': self.id}}

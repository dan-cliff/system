# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VideoShoot(models.Model):
    _name = 'video.shoot'
    _description = 'Video Shoot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start'
    _date_name = 'date_start'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(string='Shoot Name', required=True, tracking=True)
    production_id = fields.Many2one(
        'video.production',
        string='Production',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────
    date_start = fields.Datetime(
        string='Shoot Start',
        required=True,
        tracking=True,
    )
    date_stop = fields.Datetime(
        string='Shoot End',
        required=True,
        tracking=True,
    )
    duration_hours = fields.Float(
        string='Duration (h)',
        compute='_compute_duration',
        store=True,
    )
    location = fields.Char(string='Location', tracking=True)
    location_notes = fields.Text(string='Location Notes / Access Info')

    # ── Status ────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ('planned', 'Planned'),
            ('confirmed', 'Confirmed'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='planned',
        tracking=True,
        copy=False,
    )

    # ── Crew & Equipment ──────────────────────────────────────────────────
    crew_ids = fields.One2many(
        'video.shoot.crew',
        'shoot_id',
        string='Crew',
    )
    equipment_ids = fields.One2many(
        'video.shoot.equipment',
        'shoot_id',
        string='Equipment',
    )

    # ── Crew count ────────────────────────────────────────────────────────
    crew_count = fields.Integer(compute='_compute_crew_count', string='Crew Members')

    # ── Notes ─────────────────────────────────────────────────────────────
    shoot_notes = fields.Text(string='Shoot Notes')
    call_sheet = fields.Html(string='Call Sheet')

    # ── Computed ──────────────────────────────────────────────────────────
    @api.depends('date_start', 'date_stop')
    def _compute_duration(self):
        for shoot in self:
            if shoot.date_start and shoot.date_stop:
                delta = shoot.date_stop - shoot.date_start
                shoot.duration_hours = delta.total_seconds() / 3600
            else:
                shoot.duration_hours = 0.0

    @api.depends('crew_ids')
    def _compute_crew_count(self):
        for shoot in self:
            shoot.crew_count = len(shoot.crew_ids)

    @api.constrains('date_start', 'date_stop')
    def _check_dates(self):
        for shoot in self:
            if shoot.date_start and shoot.date_stop:
                if shoot.date_stop < shoot.date_start:
                    raise UserError(_('Shoot End must be after Shoot Start.'))

    # ── Actions ───────────────────────────────────────────────────────────
    def action_confirm(self):
        self.filtered(lambda s: s.state == 'planned').write({'state': 'confirmed'})

    def action_complete(self):
        self.filtered(lambda s: s.state in ('planned', 'confirmed')).write(
            {'state': 'completed'}
        )

    def action_cancel(self):
        for shoot in self:
            if shoot.state == 'completed':
                raise UserError(_('Cannot cancel a completed shoot.'))
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.filtered(lambda s: s.state == 'cancelled').write({'state': 'planned'})


class VideoShootCrew(models.Model):
    _name = 'video.shoot.crew'
    _description = 'Shoot Crew Member'
    _order = 'sequence, id'

    shoot_id = fields.Many2one(
        'video.shoot',
        string='Shoot',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one(
        'res.users',
        string='Crew Member',
        required=True,
    )
    partner_id = fields.Many2one(
        related='user_id.partner_id',
        string='Contact',
        readonly=True,
    )
    role = fields.Selection(
        [
            ('director', 'Director'),
            ('camera', 'Camera Operator'),
            ('sound', 'Sound'),
            ('lighting', 'Lighting'),
            ('talent', 'Talent / Presenter'),
            ('producer', 'Producer'),
            ('makeup', 'Make-up / Styling'),
            ('other', 'Other'),
        ],
        string='Role',
        required=True,
        default='camera',
    )
    notes = fields.Char(string='Notes')


class VideoShootEquipment(models.Model):
    _name = 'video.shoot.equipment'
    _description = 'Shoot Equipment Line'
    _order = 'equipment_type, id'

    shoot_id = fields.Many2one(
        'video.shoot',
        string='Shoot',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Item / Description', required=True)
    equipment_type = fields.Selection(
        [
            ('camera', 'Camera'),
            ('lens', 'Lens'),
            ('audio', 'Audio / Microphone'),
            ('lighting', 'Lighting'),
            ('drone', 'Drone'),
            ('stabiliser', 'Gimbal / Stabiliser'),
            ('monitor', 'Monitor / Reference'),
            ('storage', 'Storage / Media'),
            ('power', 'Power / Battery'),
            ('accessory', 'Accessory'),
            ('other', 'Other'),
        ],
        string='Type',
        default='camera',
    )
    quantity = fields.Integer(string='Qty', default=1)
    serial_number = fields.Char(string='Serial / Asset No.')
    checked_out = fields.Boolean(string='Checked Out', default=False)
    checked_in = fields.Boolean(string='Returned', default=False)
    notes = fields.Char(string='Notes')

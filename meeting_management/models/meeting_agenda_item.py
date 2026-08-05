from odoo import models, fields, api


class MeetingAgendaItem(models.Model):
    _name = 'meeting.agenda.item'
    _description = 'Meeting Agenda Item'
    _order = 'sequence, id'

    meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Meeting',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Topic / Agenda Item', required=True)
    description = fields.Html(string='Description / Background Notes')
    item_type = fields.Selection([
        ('opening', 'Opening / Welcome'),
        ('information', 'Information / Report'),
        ('discussion', 'Discussion'),
        ('decision', 'Decision Required'),
        ('action', 'Action Item Review'),
        ('aob', 'Any Other Business'),
        ('close', 'Close / Next Meeting'),
    ], string='Item Type', default='discussion')
    presenter_id = fields.Many2one(
        'res.partner',
        string='Presenter / Lead',
    )
    duration = fields.Float(
        string='Duration (min)',
        default=10,
        help='Estimated time in minutes for this agenda item.',
    )
    # Link back to the minutes item for cross-reference
    minutes_item_ids = fields.One2many(
        'meeting.minutes.item',
        'agenda_item_id',
        string='Minutes',
    )
    has_minutes = fields.Boolean(
        string='Minutes Recorded',
        compute='_compute_has_minutes',
        store=True,
    )

    @api.depends('minutes_item_ids')
    def _compute_has_minutes(self):
        for item in self:
            item.has_minutes = bool(item.minutes_item_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        return records

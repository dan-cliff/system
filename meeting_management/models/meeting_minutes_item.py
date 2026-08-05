from odoo import models, fields, api


class MeetingMinutesItem(models.Model):
    _name = 'meeting.minutes.item'
    _description = 'Meeting Minutes Item'
    _order = 'sequence, id'

    meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Meeting',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    agenda_item_id = fields.Many2one(
        'meeting.agenda.item',
        string='Agenda Item',
        domain="[('meeting_id', '=', meeting_id)]",
        help='Link this minutes entry to its corresponding agenda item.',
    )
    name = fields.Char(
        string='Topic',
        compute='_compute_name',
        store=True,
        readonly=False,
    )
    discussion = fields.Html(string='Discussion / Notes')
    decisions = fields.Html(string='Decisions Made')
    action_item_ids = fields.One2many(
        'meeting.action.item',
        'minutes_item_id',
        string='Action Items',
    )
    action_item_count = fields.Integer(
        string='Actions',
        compute='_compute_action_item_count',
    )

    @api.depends('agenda_item_id', 'agenda_item_id.name')
    def _compute_name(self):
        for item in self:
            if not item.name and item.agenda_item_id:
                item.name = item.agenda_item_id.name

    @api.depends('action_item_ids')
    def _compute_action_item_count(self):
        for item in self:
            item.action_item_count = len(item.action_item_ids)

    @api.onchange('agenda_item_id')
    def _onchange_agenda_item_id(self):
        if self.agenda_item_id and not self.name:
            self.name = self.agenda_item_id.name

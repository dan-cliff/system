import logging
from datetime import timedelta, datetime, time
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class MeetingTemplateAgendaItem(models.Model):
    _name = 'meeting.template.agenda.item'
    _description = 'Meeting Template Agenda Item'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'meeting.template',
        string='Template',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Topic / Agenda Item', required=True)
    description = fields.Html(string='Description / Notes')
    item_type = fields.Selection([
        ('opening', 'Opening / Welcome'),
        ('information', 'Information / Report'),
        ('discussion', 'Discussion'),
        ('decision', 'Decision Required'),
        ('action', 'Action Item Review'),
        ('aob', 'Any Other Business'),
        ('close', 'Close / Next Meeting'),
    ], string='Item Type', default='discussion')
    default_duration = fields.Float(string='Default Duration (min)', default=10)
    default_presenter_id = fields.Many2one(
        'res.partner',
        string='Default Presenter',
    )


class MeetingTemplate(models.Model):
    _name = 'meeting.template'
    _description = 'Meeting Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')

    # Defaults applied when creating a meeting from this template
    default_duration = fields.Float(
        string='Default Duration (hours)',
        default=1.0,
        help='Default length of meetings using this template.',
    )
    default_location = fields.Char(string='Default Location')
    default_meeting_type = fields.Selection([
        ('in_person', 'In Person'),
        ('virtual', 'Virtual / Online'),
        ('hybrid', 'Hybrid'),
    ], string='Default Meeting Type', default='in_person')
    default_invitee_ids = fields.Many2many(
        'res.partner',
        'meeting_template_invitee_rel',
        'template_id',
        'partner_id',
        string='Default Invitees',
    )
    default_chairperson_id = fields.Many2one(
        'res.partner',
        string='Default Chairperson',
    )
    default_secretary_id = fields.Many2one(
        'res.partner',
        string='Default Secretary',
    )
    agenda_item_ids = fields.One2many(
        'meeting.template.agenda.item',
        'template_id',
        string='Standard Agenda Items',
    )

    # Auto-scheduling configuration
    auto_schedule = fields.Boolean(
        string='Auto-Schedule Next Meeting',
        help='Automatically create the next meeting when the current one is completed.',
    )
    recurrence_type = fields.Selection([
        ('weekly', 'Weekly'),
        ('fortnightly', 'Fortnightly (Every 2 Weeks)'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], string='Recurrence', default='monthly')
    recurrence_day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', help='Used for weekly/fortnightly recurrence.')
    recurrence_week_of_month = fields.Selection([
        ('1', 'First'),
        ('2', 'Second'),
        ('3', 'Third'),
        ('4', 'Fourth'),
        ('last', 'Last'),
    ], string='Week of Month', default='1',
       help='Used with monthly recurrence: e.g. "Second Tuesday of the month".')
    recurrence_day_of_month = fields.Integer(
        string='Day of Month',
        default=1,
        help='For monthly/quarterly/yearly: day number (1–31).',
    )
    default_start_hour = fields.Float(
        string='Default Start Time',
        default=9.0,
        help='Default start time in 24h decimal (e.g. 9.5 = 09:30).',
    )

    # Notification templates to auto-send
    notification_template_ids = fields.Many2many(
        'meeting.notification.template',
        'meeting_template_notif_rel',
        'template_id',
        'notif_template_id',
        string='Default Notification Templates',
        help='These notification templates will be pre-selected on meetings created from this template.',
    )

    meeting_count = fields.Integer(
        string='Meetings',
        compute='_compute_meeting_count',
    )

    @api.depends()
    def _compute_meeting_count(self):
        for tmpl in self:
            tmpl.meeting_count = self.env['meeting.meeting'].search_count(
                [('template_id', '=', tmpl.id)]
            )

    def action_view_meetings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Meetings: %s') % self.name,
            'res_model': 'meeting.meeting',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }

    def _compute_next_date(self, from_date):
        """Compute the next recurrence date from from_date (datetime)."""
        self.ensure_one()
        h = int(self.default_start_hour)
        m = int(round((self.default_start_hour - h) * 60))

        if self.recurrence_type == 'weekly':
            days_ahead = 7
            next_dt = from_date + timedelta(days=days_ahead)
        elif self.recurrence_type == 'fortnightly':
            next_dt = from_date + timedelta(days=14)
        elif self.recurrence_type == 'monthly':
            # Same day next month
            month = from_date.month + 1
            year = from_date.year
            if month > 12:
                month = 1
                year += 1
            day = min(self.recurrence_day_of_month or from_date.day, 28)
            next_dt = from_date.replace(year=year, month=month, day=day)
        elif self.recurrence_type == 'quarterly':
            month = from_date.month + 3
            year = from_date.year
            while month > 12:
                month -= 12
                year += 1
            day = min(self.recurrence_day_of_month or from_date.day, 28)
            next_dt = from_date.replace(year=year, month=month, day=day)
        elif self.recurrence_type == 'yearly':
            next_dt = from_date.replace(year=from_date.year + 1)
        else:
            next_dt = from_date + timedelta(days=30)

        return next_dt.replace(hour=h, minute=m, second=0, microsecond=0)

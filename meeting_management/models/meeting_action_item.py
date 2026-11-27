import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MeetingActionItem(models.Model):
    _name = 'meeting.action.item'
    _description = 'Meeting Action Item'
    _order = 'due_date, id'

    meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Meeting',
        required=True,
        ondelete='cascade',
        index=True,
    )
    minutes_item_id = fields.Many2one(
        'meeting.minutes.item',
        string='Minutes Item',
        domain="[('meeting_id', '=', meeting_id)]",
        ondelete='set null',
    )
    name = fields.Char(string='Action', required=True)
    description = fields.Text(string='Details')
    assigned_to_id = fields.Many2one(
        'res.partner',
        string='Assigned To',
        index=True,
    )
    due_date = fields.Date(string='Due Date')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Important'),
    ], string='Priority', default='0')
    state = fields.Selection([
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='open', required=True)
    activity_id = fields.Many2one(
        'mail.activity',
        string='To-Do Activity',
        readonly=True,
        ondelete='set null',
        help='To-Do activity scheduled on the meeting for the assignee of this action item.',
    )

    def _assigned_user(self):
        self.ensure_one()
        if not self.assigned_to_id:
            return self.env.user
        return self.env['res.users'].search(
            [('partner_id', '=', self.assigned_to_id.id)], limit=1
        ) or self.env.user

    def action_create_todo(self):
        """Schedule a To-Do activity on the meeting for the action item's assignee."""
        self.ensure_one()
        if self.activity_id:
            raise UserError(_('A To-Do activity already exists for this action item.'))
        activity = self.meeting_id.activity_schedule(
            'mail.mail_activity_data_todo',
            date_deadline=self.due_date or fields.Date.context_today(self),
            summary=self.name,
            note=self.description or '',
            user_id=self._assigned_user().id,
        )
        self.activity_id = activity
        return True

    def action_mark_done(self):
        self.write({'state': 'done'})
        self.activity_id.action_feedback(feedback=_('Action item marked as done.'))

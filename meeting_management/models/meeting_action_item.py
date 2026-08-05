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
    task_id = fields.Many2one(
        'project.task',
        string='To-Do Task',
        readonly=True,
        help='Linked Odoo To-Do task created from this action item.',
    )
    task_state = fields.Char(
        string='To-Do Status',
        compute='_compute_task_state',
    )

    @api.depends('task_id', 'task_id.stage_id')
    def _compute_task_state(self):
        for item in self:
            if item.task_id:
                item.task_state = item.task_id.stage_id.name or ''
            else:
                item.task_state = ''

    def action_create_todo(self):
        """Create a personal To-Do task linked to this action item."""
        self.ensure_one()
        if self.task_id:
            raise UserError(_('A To-Do task already exists for this action item.'))

        # Find the personal stage (To-Do uses project.task with no project)
        Stage = self.env['project.task.type']
        stage = Stage.search([('name', 'ilike', 'To Do')], limit=1)
        if not stage:
            stage = Stage.search([], limit=1)

        # Determine user from partner
        user = self.env['res.users'].search(
            [('partner_id', '=', self.assigned_to_id.id)], limit=1
        ) if self.assigned_to_id else self.env.user

        task_vals = {
            'name': self.name,
            'description': self.description or '',
            'date_deadline': self.due_date,
            'user_ids': [(4, user.id)],
            'priority': self.priority or '0',
            'project_id': False,  # Personal task = To-Do
        }
        if stage:
            task_vals['stage_id'] = stage.id

        task = self.env['project.task'].create(task_vals)
        self.task_id = task.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': task.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_todo(self):
        """Open the linked To-Do task."""
        self.ensure_one()
        if not self.task_id:
            return self.action_create_todo()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': self.task_id.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_mark_done(self):
        self.write({'state': 'done'})
        for item in self.filtered('task_id'):
            done_stage = self.env['project.task.type'].search(
                [('name', 'ilike', 'done')], limit=1
            )
            if done_stage:
                item.task_id.stage_id = done_stage

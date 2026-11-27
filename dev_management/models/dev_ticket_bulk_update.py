from odoo import api, fields, models
from odoo.exceptions import UserError

# Each "Change ..." box and the ticket field it writes.
BULK_FIELDS = {
    'update_epic': 'epic_id',
    'update_user': 'user_id',
    'update_type': 'type_id',
    'update_release': 'release_id',
    'update_story_points': 'story_points',
    'update_date_deadline': 'date_deadline',
    'update_company': 'company_id',
}


class DevTicketBulkUpdate(models.TransientModel):
    """Change several fields on the selected tickets at once, like Jira's bulk edit.

    Only the ticked fields are written: a ticked field left empty is cleared.
    """
    _name = 'dev.ticket.bulk.update'
    _description = 'Bulk Update Tickets'

    ticket_ids = fields.Many2many('dev.ticket', string='Tickets',
                                  default=lambda self: self.env.context.get('active_ids'))
    ticket_count = fields.Integer('Ticket Count', compute='_compute_ticket_count')

    update_epic = fields.Boolean('Change Epic')
    epic_id = fields.Many2one('dev.epic', 'Epic')
    update_user = fields.Boolean('Change Assignee')
    user_id = fields.Many2one('res.users', 'Assignee', domain=[('share', '=', False)])
    update_type = fields.Boolean('Change Type')
    type_id = fields.Many2one('dev.ticket.type', 'Type')
    update_release = fields.Boolean('Change Release')
    release_id = fields.Many2one('dev.release', 'Release')
    update_story_points = fields.Boolean('Change Story Points')
    story_points = fields.Float('Story Points')
    update_date_deadline = fields.Boolean('Change Due Date')
    date_deadline = fields.Date('Due Date')
    update_company = fields.Boolean('Change Company')
    company_id = fields.Many2one('res.company', 'Company', domain=lambda self: [('id', 'in', self.env.companies.ids)])

    # Technical modes, not user options.
    tag_mode = fields.Selection([
        ('none', 'Keep'), ('add', 'Add'), ('remove', 'Remove'), ('replace', 'Replace All With'),
    ], 'Labels', default='none', required=True)
    tag_ids = fields.Many2many('dev.tag', string='Labels to Change')
    sprint_mode = fields.Selection([
        ('none', 'Keep'), ('add', 'Add to Sprint'), ('remove', 'Remove from Sprint'), ('replace', 'Replace Sprint'),
    ], 'Sprints', default='none', required=True)
    sprint_ids = fields.Many2many('dev.sprint', 'dev_ticket_bulk_update_sprint_rel', 'wizard_id', 'sprint_id',
                                  string='Sprint', help='The sprints to add, to remove, or to replace with.')
    sprint_from_ids = fields.Many2many('dev.sprint', 'dev_ticket_bulk_update_sprint_from_rel', 'wizard_id',
                                       'sprint_id', string='Replace',
                                       help='The sprints to take the tickets out of. Left empty, every planned '
                                            'or active sprint they are in is replaced; completed sprints are kept '
                                            'as history.')

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for wizard in self:
            wizard.ticket_count = len(wizard.ticket_ids)

    def _bulk_values(self):
        """The values written to every ticket, from the ticked fields."""
        vals = {}
        for toggle, name in BULK_FIELDS.items():
            if self[toggle]:
                vals[name] = self[name].id if self._fields[name].type == 'many2one' else self[name]
        if self.update_company and not self.company_id:
            raise UserError(self.env._('Pick the Company the tickets move to: a ticket always has one.'))
        if self.tag_mode != 'none' and (self.tag_ids or self.tag_mode == 'replace'):
            vals['tag_ids'] = {
                'add': [(4, tag.id) for tag in self.tag_ids],
                'remove': [(3, tag.id) for tag in self.tag_ids],
                'replace': [(6, 0, self.tag_ids.ids)],
            }[self.tag_mode]
        return vals

    def _bulk_update_sprints(self, tickets):
        if self.sprint_mode == 'none':
            return
        if self.sprint_mode == 'add' and not self.sprint_ids:
            raise UserError(self.env._('Pick the sprint to add the tickets to.'))
        if self.sprint_mode == 'remove' and not self.sprint_ids:
            raise UserError(self.env._('Pick the sprint to remove the tickets from.'))
        # Replacing with no sprint takes the tickets back to the backlog.
        if self.sprint_mode == 'add':
            tickets.write({'sprint_ids': [(4, sprint.id) for sprint in self.sprint_ids]})
        elif self.sprint_mode == 'remove':
            tickets.write({'sprint_ids': [(3, sprint.id) for sprint in self.sprint_ids]})
        else:
            for ticket in tickets:
                old = (ticket.sprint_ids & self.sprint_from_ids) if self.sprint_from_ids \
                    else ticket.sprint_ids.filtered(lambda s: s.state != 'closed')
                commands = [(3, sprint.id) for sprint in old - self.sprint_ids]
                commands += [(4, sprint.id) for sprint in self.sprint_ids - ticket.sprint_ids]
                if commands:
                    ticket.write({'sprint_ids': commands})

    def _bulk_apply(self, tickets):
        vals = self._bulk_values()
        if vals:
            tickets.write(vals)
        self._bulk_update_sprints(tickets)

    def action_apply(self):
        self.ensure_one()
        if not self.ticket_ids:
            raise UserError(self.env._('Select the tickets to update first.'))
        self._bulk_apply(self.ticket_ids)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('%s tickets updated.', len(self.ticket_ids)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

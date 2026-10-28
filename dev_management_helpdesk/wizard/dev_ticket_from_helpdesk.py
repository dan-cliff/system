from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Helpdesk priority (stars) -> development priority.
PRIORITY_XMLIDS = {
    '3': 'dev_management.priority_highest',
    '2': 'dev_management.priority_high',
    '1': 'dev_management.priority_medium',
    '0': 'dev_management.priority_low',
}


class DevTicketFromHelpdesk(models.TransientModel):
    _name = 'dev.ticket.from.helpdesk'
    _description = 'Create Development Tickets from a Helpdesk Ticket'

    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', required=True, readonly=True)
    line_ids = fields.One2many('dev.ticket.from.helpdesk.line', 'wizard_id', string='New Tickets')
    existing_ticket_ids = fields.Many2many('dev.ticket', string='Link Existing Tickets',
                                           help='Development tickets that already cover this request.')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        ticket = self.env['helpdesk.ticket'].browse(values.get('helpdesk_ticket_id'))
        if ticket and 'line_ids' in fields_list:
            values['line_ids'] = [(0, 0, self._line_values(ticket))]
        return values

    @api.model
    def _line_values(self, ticket):
        bug = self.env.ref('dev_management.ticket_type_bug', raise_if_not_found=False)
        priority = self.env.ref(PRIORITY_XMLIDS.get(ticket.priority, ''), raise_if_not_found=False) \
            if ticket.priority in PRIORITY_XMLIDS else False
        intro = Markup('<p><em>%s</em></p>') % _('Raised from Helpdesk ticket %(ticket)s (customer: %(customer)s).',
                                                 ticket=ticket.display_name,
                                                 customer=ticket.partner_id.display_name or ticket.partner_name or '-')
        return {
            'name': ticket.name,
            'type_id': bug.id if bug else False,
            'priority_id': priority.id if priority else False,
            'description': intro + (ticket.description or Markup('')),
        }

    def action_create(self):
        self.ensure_one()
        if not self.line_ids and not self.existing_ticket_ids:
            raise UserError(_('Add at least one ticket to create, or pick existing tickets to link.'))
        helpdesk_ticket = self.helpdesk_ticket_id
        created = self.env['dev.ticket']
        for line in self.line_ids:
            created |= self.env['dev.ticket'].create({
                'name': line.name,
                'type_id': line.type_id.id,
                'priority_id': line.priority_id.id or self.env['dev.ticket']._fields['priority_id'].default(
                    self.env['dev.ticket']).id,
                'description': line.description,
                'release_id': line.release_id.id,
                'feature_id': line.feature_id.id,
                'user_id': line.user_id.id,
                'company_id': helpdesk_ticket.company_id.id or self.env.company.id,
            })
        tickets = created | self.existing_ticket_ids
        helpdesk_ticket.write({'dev_ticket_ids': [(4, ticket.id) for ticket in tickets]})
        for ticket in created:
            ticket.message_post(body=_('Raised from Helpdesk ticket %s.', helpdesk_ticket.display_name))
        helpdesk_ticket.message_post(
            body=Markup('<p>%s</p><ul>%s</ul>') % (
                _('Development tickets linked:'),
                Markup('').join(Markup('<li>%s</li>') % t.display_name for t in tickets)),
            subtype_id=self.env.ref('mail.mt_note').id)
        if len(created) == 1 and not self.existing_ticket_ids:
            return {'type': 'ir.actions.act_window', 'res_model': 'dev.ticket', 'res_id': created.id,
                    'view_mode': 'form'}
        return helpdesk_ticket.action_open_dev_tickets()


class DevTicketFromHelpdeskLine(models.TransientModel):
    _name = 'dev.ticket.from.helpdesk.line'
    _description = 'Development Ticket to Create from a Helpdesk Ticket'

    wizard_id = fields.Many2one('dev.ticket.from.helpdesk', required=True, ondelete='cascade')
    name = fields.Char('Summary', required=True)
    type_id = fields.Many2one('dev.ticket.type', 'Type')
    priority_id = fields.Many2one('dev.priority', 'Priority')
    description = fields.Html()
    release_id = fields.Many2one('dev.release', 'Release', domain="[('state', 'not in', ('closed', 'cancelled'))]")
    feature_id = fields.Many2one('dev.feature', 'Feature')
    user_id = fields.Many2one('res.users', 'Assignee', domain=[('share', '=', False)])

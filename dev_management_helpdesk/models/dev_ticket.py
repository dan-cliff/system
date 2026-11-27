from markupsafe import Markup

from odoo import _, api, fields, models


class DevTicket(models.Model):
    _inherit = 'dev.ticket'

    helpdesk_ticket_ids = fields.Many2many(
        'helpdesk.ticket', 'dev_ticket_helpdesk_ticket_rel', 'dev_ticket_id', 'helpdesk_ticket_id',
        string='Helpdesk Tickets', groups='helpdesk_management.group_helpdesk_user',
        help='The customer requests this ticket came from.')
    helpdesk_ticket_count = fields.Integer('Helpdesk Ticket Count', compute='_compute_helpdesk_ticket_count',
                                           groups='helpdesk_management.group_helpdesk_user')

    @api.depends('helpdesk_ticket_ids')
    def _compute_helpdesk_ticket_count(self):
        for ticket in self:
            ticket.helpdesk_ticket_count = len(ticket.helpdesk_ticket_ids)

    def write(self, vals):
        closing = self.browse()
        if vals.get('stage_id') and self.env['dev.ticket.stage'].browse(vals['stage_id']).is_closed:
            closing = self.filtered(lambda t: not t.is_closed)
        result = super().write(vals)
        for ticket in closing:
            ticket._notify_helpdesk(_('Development ticket %(key)s "%(name)s" is done (%(stage)s).',
                                      key=ticket.key, name=ticket.name, stage=ticket.stage_id.name))
        return result

    def _notify_helpdesk(self, message):
        """Internal note on the linked Helpdesk tickets."""
        self.ensure_one()
        subtype = self.env.ref('mail.mt_note')
        for helpdesk_ticket in self.sudo().helpdesk_ticket_ids:
            helpdesk_ticket.message_post(body=Markup('<p>%s</p>') % message, subtype_id=subtype.id)

    def action_open_helpdesk_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Helpdesk Tickets'),
            'res_model': 'helpdesk.ticket',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.helpdesk_ticket_ids.ids)],
        }


class DevRelease(models.Model):
    _inherit = 'dev.release'

    def write(self, vals):
        result = super().write(vals)
        if vals.get('state') == 'core':
            for release in self:
                for ticket in release.ticket_ids:
                    ticket._notify_helpdesk(_('Development ticket %(key)s "%(name)s" has been released in %(release)s.',
                                              key=ticket.key, name=ticket.name, release=release.display_name))
        return result


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    dev_ticket_ids = fields.Many2many(
        'dev.ticket', 'dev_ticket_helpdesk_ticket_rel', 'helpdesk_ticket_id', 'dev_ticket_id',
        string='Dev Tickets', groups='dev_management.group_dev_user')
    dev_ticket_count = fields.Integer('Dev Ticket Count', compute='_compute_dev_ticket_count',
                                      groups='dev_management.group_dev_user')

    @api.depends('dev_ticket_ids')
    def _compute_dev_ticket_count(self):
        for ticket in self:
            ticket.dev_ticket_count = len(ticket.dev_ticket_ids)

    def action_create_dev_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Dev Tickets'),
            'res_model': 'dev.ticket.from.helpdesk',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_helpdesk_ticket_id': self.id},
        }

    def action_open_dev_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(domain=[('id', 'in', self.dev_ticket_ids.ids)], context={})
        return action

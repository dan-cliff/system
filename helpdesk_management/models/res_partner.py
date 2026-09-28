from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    helpdesk_ticket_count = fields.Integer('Tickets', compute='_compute_helpdesk_ticket_count')

    def _compute_helpdesk_ticket_count(self):
        Ticket = self.env['helpdesk.ticket']
        if not Ticket.has_access('read'):
            self.helpdesk_ticket_count = 0
            return
        # count each company's tickets together with its contacts'
        all_partners = self.with_context(active_test=False).search_fetch(
            [('id', 'child_of', self.ids)], ['parent_id'])
        counts = Ticket._read_group([('partner_id', 'in', all_partners.ids)], ['partner_id'], ['__count'])
        self.helpdesk_ticket_count = 0
        for partner, count in counts:
            while partner:
                if partner in self:
                    partner.helpdesk_ticket_count += count
                partner = partner.parent_id

    def action_open_helpdesk_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_ticket_action_main')
        action.update(
            domain=[('partner_id', 'child_of', self.id)],
            context={'default_partner_id': self.id},
            name=_('Tickets'),
        )
        return action

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class DevSuggestionFromHelpdesk(models.TransientModel):
    _name = 'dev.suggestion.from.helpdesk'
    _description = 'Feature Suggestion from a Helpdesk Ticket'

    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', required=True, readonly=True)
    link_existing = fields.Boolean('Vote on an Existing Suggestion',
                                   help='Add the customer\'s vote to a suggestion that already asks for this.')
    suggestion_id = fields.Many2one('dev.suggestion', 'Suggestion', domain=[('merged_into_id', '=', False)])
    name = fields.Char('Title')
    description = fields.Html()
    category_id = fields.Many2one('dev.suggestion.category', 'Category')
    partner_id = fields.Many2one('res.partner', 'Customer', help='Their vote is added to the suggestion.')
    importance_id = fields.Many2one('dev.suggestion.importance', 'Importance',
                                    default=lambda self: self.env['dev.suggestion.importance'].search([], limit=1))
    note = fields.Text('Why It Matters')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        ticket = self.env['helpdesk.ticket'].browse(values.get('helpdesk_ticket_id'))
        if ticket:
            values.setdefault('name', ticket.name)
            values.setdefault('description', ticket.description)
            values.setdefault('partner_id', ticket.partner_id.id)
            values.setdefault('note', (html2plaintext(ticket.description or '') or ticket.name)[:1000])
        return values

    def action_confirm(self):
        self.ensure_one()
        source = self.env.ref('dev_feature_suggestions.source_helpdesk')
        ticket = self.helpdesk_ticket_id
        if self.link_existing:
            if not self.suggestion_id:
                raise UserError(_('Choose the suggestion to vote on.'))
            suggestion = self.suggestion_id
        else:
            if not self.name:
                raise UserError(_('Give the suggestion a title.'))
            suggestion = self.env['dev.suggestion'].create({
                'name': self.name,
                'description': self.description,
                'category_id': self.category_id.id,
                'partner_id': self.partner_id.id,
                'source_id': source.id,
                'company_id': ticket.company_id.id or self.env.company.id,
            })
        if self.partner_id:
            suggestion._add_vote(self.partner_id, importance=self.importance_id, note=self.note, source=source)
        ticket.write({'suggestion_ids': [(4, suggestion.id)]})
        ticket.message_post(body=Markup('<p>%s</p>') % _('Feature suggestion: %s', suggestion.display_name),
                            subtype_id=self.env.ref('mail.mt_note').id)
        suggestion.sudo().message_post(body=_('Customer request from Helpdesk ticket %s.', ticket.display_name),
                                       subtype_id=self.env.ref('mail.mt_note').id)
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.suggestion', 'res_id': suggestion.id,
                'view_mode': 'form'}

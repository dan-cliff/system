from odoo import _, api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    suggestion_ids = fields.Many2many(
        'dev.suggestion', 'dev_suggestion_helpdesk_ticket_rel', 'helpdesk_ticket_id', 'suggestion_id',
        string='Feature Suggestions', groups='dev_feature_suggestions.group_suggestion_user')
    suggestion_count = fields.Integer('Suggestion Count', compute='_compute_suggestion_count',
                                      groups='dev_feature_suggestions.group_suggestion_user')

    @api.depends('suggestion_ids')
    def _compute_suggestion_count(self):
        for ticket in self:
            ticket.suggestion_count = len(ticket.suggestion_ids)

    def action_create_suggestion(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Feature Suggestion'),
            'res_model': 'dev.suggestion.from.helpdesk',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_helpdesk_ticket_id': self.id},
        }

    def action_open_suggestions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_feature_suggestions.dev_suggestion_action')
        action.update(domain=[('id', 'in', self.suggestion_ids.ids)], context={})
        return action


class DevSuggestion(models.Model):
    _inherit = 'dev.suggestion'

    helpdesk_ticket_ids = fields.Many2many(
        'helpdesk.ticket', 'dev_suggestion_helpdesk_ticket_rel', 'suggestion_id', 'helpdesk_ticket_id',
        string='Helpdesk Tickets', groups='helpdesk_management.group_helpdesk_user')

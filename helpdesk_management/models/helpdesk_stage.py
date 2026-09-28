from odoo import api, fields, models


class HelpdeskStage(models.Model):
    _name = 'helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, id'

    def _default_team_ids(self):
        team_id = self.env.context.get('default_team_id')
        return [(4, team_id)] if team_id else []

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean(
        string='Closing Stage',
        help='Tickets in this stage are closed: they are folded in the kanban view, '
             'no longer count as open and stop their SLA clocks.')
    team_ids = fields.Many2many(
        'helpdesk.team', 'helpdesk_stage_team_rel', 'stage_id', 'team_id',
        string='Teams', default=_default_team_ids)
    template_id = fields.Many2one(
        'mail.template', string='Email Template',
        domain=[('model', '=', 'helpdesk.ticket')],
        help='Emailed to the customer when a ticket reaches this stage.')
    rating_template_id = fields.Many2one(
        'mail.template', string='Rating Request',
        domain=[('model', '=', 'helpdesk.ticket')],
        help='Emailed to the customer, asking them to rate the service, when a ticket reaches '
             'this stage. Only sent for teams with Customer Ratings enabled.')
    ticket_count = fields.Integer(compute='_compute_ticket_count')

    @api.depends('team_ids')
    def _compute_ticket_count(self):
        counts = dict(self.env['helpdesk.ticket']._read_group(
            [('stage_id', 'in', self.ids)], ['stage_id'], ['__count']))
        for stage in self:
            stage.ticket_count = counts.get(stage, 0)

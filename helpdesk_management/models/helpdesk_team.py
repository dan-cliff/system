import ast
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTeam(models.Model):
    _name = 'helpdesk.team'
    _description = 'Helpdesk Team'
    _inherit = ['mail.alias.mixin', 'mail.thread', 'rating.parent.mixin']
    _order = 'sequence, name'
    _rating_satisfaction_days = 30

    def _default_stage_ids(self):
        xmlids = ['stage_new', 'stage_in_progress', 'stage_on_hold', 'stage_solved', 'stage_cancelled']
        stages = self.env['helpdesk.stage']
        for xmlid in xmlids:
            stages |= self.env.ref(f'helpdesk_management.{xmlid}', raise_if_not_found=False) or stages.browse()
        return stages.filtered('active')

    name = fields.Char(required=True, translate=True, tracking=True)
    description = fields.Html(translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer('Color Index')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    member_ids = fields.Many2many(
        'res.users', 'helpdesk_team_member_rel', 'team_id', 'user_id', string='Team Members',
        domain=[('share', '=', False)], default=lambda self: self.env.user,
        help='Agents who work on the team\'s tickets. New tickets are assigned among them.')
    assign_method = fields.Selection([
        ('manual', 'Manually'),
        ('randomly', 'Round Robin'),
        ('balanced', 'Balanced'),
    ], string='Assignment Method', default='manual', required=True,
        help='How new tickets are assigned to team members:\n'
             '- Manually: tickets stay unassigned until someone takes them.\n'
             '- Round Robin: each member gets the same number of tickets, in turn.\n'
             '- Balanced: the member with the fewest open tickets gets the next one.')
    stage_ids = fields.Many2many(
        'helpdesk.stage', 'helpdesk_stage_team_rel', 'team_id', 'stage_id',
        string='Stages', default=_default_stage_ids)
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Hours',
        default=lambda self: self.env.company.resource_calendar_id,
        help='SLA deadlines and time-to-close are counted in these working hours.')
    ticket_ids = fields.One2many('helpdesk.ticket', 'team_id', string='Tickets')

    use_sla = fields.Boolean('Use SLA Policies', default=True)
    sla_ids = fields.One2many('helpdesk.sla', 'team_id', string='SLA Policies')
    use_rating = fields.Boolean(
        'Customer Ratings',
        help='Ask customers to rate the service when a ticket reaches a stage with a Rating Request.')
    use_website_form = fields.Boolean(
        'Website Form', help='Publish a "Submit a Ticket" form for this team at /helpdesk.')
    website_form_url = fields.Char(compute='_compute_website_form_url')
    allow_portal_ticket_closing = fields.Boolean(
        'Closure by Customers', help='Customers can close their own tickets from the portal.')
    auto_close_ticket = fields.Boolean(
        'Automatic Closing',
        help='Move tickets that have not changed stage for a number of days to a closing stage.')
    auto_close_day = fields.Integer('Inactive Period (days)', default=7)
    from_stage_ids = fields.Many2many(
        'helpdesk.stage', 'helpdesk_team_auto_close_stage_rel', 'team_id', 'stage_id',
        string='In Stages', domain="[('id', 'in', stage_ids)]",
        help='Only close tickets in these stages. Leave empty for every open stage.')
    to_stage_id = fields.Many2one(
        'helpdesk.stage', string='Move to Stage',
        domain="[('id', 'in', stage_ids), ('fold', '=', True)]")

    open_ticket_count = fields.Integer(compute='_compute_ticket_counts')
    unassigned_ticket_count = fields.Integer(compute='_compute_ticket_counts')
    urgent_ticket_count = fields.Integer(compute='_compute_ticket_counts')
    my_ticket_count = fields.Integer(compute='_compute_ticket_counts')
    sla_failed_ticket_count = fields.Integer(compute='_compute_ticket_counts')

    @api.constrains('auto_close_ticket', 'auto_close_day', 'to_stage_id')
    def _check_auto_close(self):
        for team in self.filtered('auto_close_ticket'):
            if team.auto_close_day < 1:
                raise ValidationError(_('The inactive period of team %s must be at least one day.', team.name))
            if not team.to_stage_id:
                raise ValidationError(_('Choose the stage team %s moves inactive tickets to.', team.name))

    def write(self, vals):
        res = super().write(vals)
        if 'resource_calendar_id' in vals:
            self.env['helpdesk.sla.status'].search([('team_id', 'in', self.ids)])._update_deadlines()
        return res

    def _compute_website_form_url(self):
        for team in self:
            team.website_form_url = f'/helpdesk/{team.id}' if team.id else False

    def _compute_ticket_counts(self):
        Ticket = self.env['helpdesk.ticket']
        base = [('team_id', 'in', self.ids), ('fold', '=', False)]

        def count(domain):
            return {team.id: n for team, n in Ticket._read_group(base + domain, ['team_id'], ['__count'])}

        open_counts = count([])
        unassigned = count([('user_id', '=', False)])
        urgent = count([('priority', '=', '3')])
        mine = count([('user_id', '=', self.env.uid)])
        failed = count([('sla_fail', '=', True)])
        for team in self:
            team.open_ticket_count = open_counts.get(team.id, 0)
            team.unassigned_ticket_count = unassigned.get(team.id, 0)
            team.urgent_ticket_count = urgent.get(team.id, 0)
            team.my_ticket_count = mine.get(team.id, 0)
            team.sla_failed_ticket_count = failed.get(team.id, 0)

    # ------------------------------------------------------------
    # Email alias
    # ------------------------------------------------------------

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('helpdesk.ticket').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or '{}')
            defaults['team_id'] = self.id
        return values

    # ------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------

    def _determine_user_to_assign(self):
        """The member each team would give its next ticket to, as {team: user}
        (an empty recordset when the team assigns manually or has no members)."""
        Ticket = self.env['helpdesk.ticket'].sudo()
        result = {}
        for team in self:
            members = team.member_ids.filtered('active')
            user = self.env['res.users']
            if team.assign_method == 'randomly' and members:
                ids = sorted(members.ids)
                last = Ticket.search([('team_id', '=', team.id), ('user_id', 'in', ids)],
                                     order='assign_date desc, id desc', limit=1)
                index = (ids.index(last.user_id.id) + 1) % len(ids) if last else 0
                user = user.browse(ids[index])
            elif team.assign_method == 'balanced' and members:
                open_counts = dict(Ticket._read_group(
                    [('team_id', '=', team.id), ('user_id', 'in', members.ids), ('fold', '=', False)],
                    ['user_id'], ['__count']))
                user = min(members.sorted('id'), key=lambda u: open_counts.get(u, 0))
            result[team] = user
        return result

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def _action_tickets(self, name, extra_context=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_ticket_action_team')
        context = {
            'default_team_id': self.id,
            'search_default_team_id': self.id,
            'search_default_is_open': 1,
        }
        context.update(extra_context or {})
        action.update(name=name, display_name=name, context=context)
        return action

    def action_view_tickets(self):
        return self._action_tickets(self.name)

    def action_view_unassigned_tickets(self):
        return self._action_tickets(_('Unassigned Tickets'), {'search_default_unassigned': 1})

    def action_view_urgent_tickets(self):
        return self._action_tickets(_('Urgent Tickets'), {'search_default_urgent': 1})

    def action_view_my_tickets(self):
        return self._action_tickets(_('My Tickets'), {'search_default_my_tickets': 1})

    def action_view_sla_failed_tickets(self):
        return self._action_tickets(_('Failed SLA Tickets'), {'search_default_sla_failed': 1})

    def action_view_ratings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_rating_action')
        action['domain'] = [('parent_res_model', '=', 'helpdesk.team'), ('parent_res_id', '=', self.id)]
        return action

    def action_open_website_form(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.website_form_url, 'target': 'new'}

    # ------------------------------------------------------------
    # Automatic closing
    # ------------------------------------------------------------

    @api.model
    def _cron_auto_close_tickets(self):
        for team in self.search([('auto_close_ticket', '=', True), ('to_stage_id', '!=', False)]):
            domain = [
                ('team_id', '=', team.id),
                ('fold', '=', False),
                ('date_last_stage_update', '<', fields.Datetime.now() - timedelta(days=team.auto_close_day)),
            ]
            if team.from_stage_ids:
                domain.append(('stage_id', 'in', team.from_stage_ids.ids))
            tickets = self.env['helpdesk.ticket'].search(domain)
            if tickets:
                tickets.write({'stage_id': team.to_stage_id.id})

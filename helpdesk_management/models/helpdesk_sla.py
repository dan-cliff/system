from datetime import timedelta

from odoo import _, api, fields, models
from odoo.fields import Domain

from .helpdesk_ticket import TICKET_PRIORITY


class HelpdeskSla(models.Model):
    _name = 'helpdesk.sla'
    _description = 'Helpdesk SLA Policy'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    description = fields.Html(translate=True)
    active = fields.Boolean(default=True)
    team_id = fields.Many2one('helpdesk.team', string='Team', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='team_id.company_id', store=True)
    stage_id = fields.Many2one(
        'helpdesk.stage', string='Target Stage', required=True,
        domain="[('team_ids', 'in', team_id)]",
        help='The SLA is reached when a ticket gets to this stage, or any stage after it.')
    time = fields.Float(
        'Within (working hours)', required=True,
        help='Working hours, from when the ticket is created, to reach the target stage.')
    priority = fields.Selection(
        TICKET_PRIORITY, string='Priority',
        help='Only for tickets of this priority. Leave empty for every priority.')
    ticket_type_ids = fields.Many2many(
        'helpdesk.ticket.type', string='Ticket Types',
        help='Only for tickets of these types. Leave empty for every type.')
    tag_ids = fields.Many2many(
        'helpdesk.tag', string='Tags',
        help='Only for tickets with at least one of these tags. Leave empty for every ticket.')
    partner_ids = fields.Many2many(
        'res.partner', string='Customers',
        help='Only for tickets from these customers (or their contacts). Leave empty for every customer.')
    ticket_count = fields.Integer(compute='_compute_ticket_count')

    _time_positive = models.Constraint('CHECK (time >= 0)', 'The SLA time cannot be negative.')

    def write(self, vals):
        res = super().write(vals)
        if 'time' in vals:
            self.env['helpdesk.sla.status'].search([('sla_id', 'in', self.ids)])._update_deadlines()
        return res

    def _compute_ticket_count(self):
        counts = dict(self.env['helpdesk.sla.status']._read_group(
            [('sla_id', 'in', self.ids), ('ticket_id.fold', '=', False)], ['sla_id'], ['__count']))
        for sla in self:
            sla.ticket_count = counts.get(sla, 0)

    def _applies_to(self, ticket):
        self.ensure_one()
        return (
            self.team_id == ticket.team_id
            and (not self.priority or self.priority == ticket.priority)
            and (not self.ticket_type_ids or ticket.ticket_type_id in self.ticket_type_ids)
            and (not self.tag_ids or bool(self.tag_ids & ticket.tag_ids))
            and (not self.partner_ids or ticket.partner_id.commercial_partner_id
                 in self.partner_ids.commercial_partner_id)
        )

    def action_view_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_ticket_action_main')
        action.update(
            domain=[('sla_status_ids.sla_id', '=', self.id)],
            context={'search_default_is_open': 1},
            name=_('Tickets under %s', self.name),
        )
        return action


class HelpdeskSlaStatus(models.Model):
    _name = 'helpdesk.sla.status'
    _description = 'Ticket SLA Status'
    _order = 'deadline, id'
    _rec_name = 'sla_id'

    ticket_id = fields.Many2one('helpdesk.ticket', required=True, ondelete='cascade', index=True)
    sla_id = fields.Many2one('helpdesk.sla', string='SLA Policy', required=True, ondelete='cascade')
    sla_stage_id = fields.Many2one(related='sla_id.stage_id', string='Target Stage', store=True)
    team_id = fields.Many2one(related='ticket_id.team_id', store=True)
    user_id = fields.Many2one(related='ticket_id.user_id', string='Assigned to', store=True)
    priority = fields.Selection(related='ticket_id.priority', store=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True)
    deadline = fields.Datetime(required=True, readonly=True)
    reached_datetime = fields.Datetime('Reached On', copy=False)
    status = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('reached', 'Reached'),
        ('failed', 'Failed'),
    ], compute='_compute_status', search='_search_status')
    reached_late = fields.Boolean(compute='_compute_reached_late', store=True)
    exceeded_hours = fields.Float(
        compute='_compute_exceeded_hours', store=True,
        help='Working hours past the deadline when the SLA was reached (negative: reached early).')

    @api.model
    def _get_deadline(self, ticket, sla):
        """When `sla` falls due on `ticket`: its time in the team's working hours,
        counted from when the ticket was created."""
        start = ticket.create_date or fields.Datetime.now()
        calendar = ticket._get_working_calendar()
        deadline = calendar.plan_hours(sla.time, start, compute_leaves=True) if calendar and sla.time else False
        return deadline.replace(tzinfo=None) if deadline else start + timedelta(hours=sla.time)

    def _update_deadlines(self):
        """Recalculate deadlines (SLA time or working hours changed); SLAs already
        reached keep theirs."""
        for status in self.filtered(lambda s: not s.reached_datetime):
            status.sudo().deadline = self._get_deadline(status.ticket_id, status.sla_id)

    @api.depends('deadline', 'reached_datetime')
    def _compute_exceeded_hours(self):
        for status in self:
            if not (status.deadline and status.reached_datetime):
                status.exceeded_hours = 0.0
                continue
            calendar = status.ticket_id._get_working_calendar()
            early = status.reached_datetime < status.deadline
            start, end = sorted([status.deadline, status.reached_datetime])
            if calendar:
                hours = calendar.get_work_hours_count(start, end, compute_leaves=True)
            else:
                hours = (end - start).total_seconds() / 3600
            status.exceeded_hours = -hours if early else hours

    @api.depends('deadline', 'reached_datetime')
    def _compute_reached_late(self):
        for status in self:
            status.reached_late = bool(status.reached_datetime and status.reached_datetime > status.deadline)

    @api.depends('deadline', 'reached_datetime')
    def _compute_status(self):
        now = fields.Datetime.now()
        for status in self:
            if status.reached_datetime:
                status.status = 'reached' if status.reached_datetime <= status.deadline else 'failed'
            else:
                status.status = 'failed' if status.deadline < now else 'ongoing'

    def _search_status(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        now = fields.Datetime.now()
        domains = {
            'ongoing': Domain('reached_datetime', '=', False) & Domain('deadline', '>=', now),
            'reached': Domain('reached_datetime', '!=', False) & Domain('reached_late', '=', False),
            'failed': Domain('reached_late', '=', True)
                      | (Domain('reached_datetime', '=', False) & Domain('deadline', '<', now)),
        }
        domain = Domain.OR(domains[v] for v in value if v in domains)
        return ~domain if operator == 'not in' else domain

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.fields import Domain

# Priority stays a fixed selection: the star widget needs one, and SLA policies
# and the Urgent filters compare against these values.
TICKET_PRIORITY = [
    ('0', 'Low'),
    ('1', 'Medium'),
    ('2', 'High'),
    ('3', 'Urgent'),
]

# Changes to these fields can change which SLA policies apply to a ticket.
SLA_FIELDS = {'team_id', 'priority', 'ticket_type_id', 'tag_ids', 'partner_id'}


class HelpdeskTicket(models.Model):
    _name = 'helpdesk.ticket'
    _description = 'Helpdesk Ticket'
    _inherit = ['portal.mixin', 'mail.thread.cc', 'mail.activity.mixin', 'rating.mixin',
                'mail.tracking.duration.mixin']
    _order = 'priority desc, id desc'
    _primary_email = 'partner_email'
    _rec_names_search = ['name', 'ticket_ref', 'partner_id.name', 'partner_email']
    _track_duration_field = 'stage_id'

    def _default_team_id(self):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return self.env['helpdesk.team'].browse(team_id)
        Team = self.env['helpdesk.team']
        return (Team.search([('member_ids', 'in', self.env.uid)], limit=1)
                or Team.search([], limit=1))

    name = fields.Char('Subject', required=True, tracking=True, index='trigram')
    ticket_ref = fields.Char('Ticket Number', readonly=True, copy=False, index=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    color = fields.Integer('Color Index')
    team_id = fields.Many2one(
        'helpdesk.team', string='Team', tracking=True, index=True, default=_default_team_id)
    company_id = fields.Many2one(
        'res.company', compute='_compute_company_id', store=True, readonly=False,
        required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Assigned to', tracking=True, index=True,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True, index=True)
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id')
    partner_name = fields.Char(
        'Customer Name', compute='_compute_partner_info', store=True, readonly=False)
    partner_email = fields.Char(
        'Customer Email', compute='_compute_partner_info', store=True, readonly=False)
    partner_phone = fields.Char(
        'Customer Phone', compute='_compute_partner_info', store=True, readonly=False)
    partner_ticket_count = fields.Integer(compute='_compute_partner_ticket_count')
    priority = fields.Selection(TICKET_PRIORITY, default='0', tracking=True, index=True)
    ticket_type_id = fields.Many2one('helpdesk.ticket.type', string='Type', tracking=True)
    tag_ids = fields.Many2many('helpdesk.tag', string='Tags')
    stage_id = fields.Many2one(
        'helpdesk.stage', string='Stage', compute='_compute_stage_id', store=True, readonly=False,
        tracking=True, index=True, copy=False, ondelete='restrict', group_expand='_read_group_stage_ids',
        domain="[('team_ids', 'in', team_id)]")
    fold = fields.Boolean(related='stage_id.fold', string='Closed', store=True)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked'),
    ], string='Status', default='normal', required=True, copy=False, tracking=True)

    date_last_stage_update = fields.Datetime('Last Stage Update', readonly=True, copy=False, index=True)
    assign_date = fields.Datetime('First Assigned On', readonly=True, copy=False)
    assign_hours = fields.Float(
        'Hours to Assign', compute='_compute_assign_hours', store=True, aggregator='avg',
        help='Working hours from creation to first assignment.')
    close_date = fields.Datetime('Closed On', readonly=True, copy=False)
    close_hours = fields.Float(
        'Hours to Close', compute='_compute_close_hours', store=True, aggregator='avg',
        help='Working hours from creation to closing.')

    use_sla = fields.Boolean(related='team_id.use_sla')
    use_rating = fields.Boolean(related='team_id.use_rating')
    allow_portal_ticket_closing = fields.Boolean(related='team_id.allow_portal_ticket_closing')
    sla_status_ids = fields.One2many('helpdesk.sla.status', 'ticket_id', string='SLA Status')
    sla_deadline = fields.Datetime(
        'SLA Deadline', compute='_compute_sla', store=True, index=True,
        help='The nearest deadline of the SLA policies this ticket has not reached yet.')
    sla_reached_late = fields.Boolean(compute='_compute_sla', store=True)
    sla_fail = fields.Boolean('SLA Failed', compute='_compute_sla_fail', search='_search_sla_fail')
    sla_success = fields.Boolean('SLA Reached', compute='_compute_sla_fail', search='_search_sla_success')

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------

    @api.depends('team_id')
    def _compute_company_id(self):
        for ticket in self:
            if ticket.team_id:
                ticket.company_id = ticket.team_id.company_id

    @api.depends('team_id')
    def _compute_stage_id(self):
        for ticket in self:
            if not ticket.team_id:
                continue
            if not ticket.stage_id or ticket.stage_id not in ticket.team_id.stage_ids:
                ticket.stage_id = ticket.team_id.stage_ids[:1]

    @api.depends('partner_id')
    def _compute_partner_info(self):
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_name = ticket.partner_id.name
                ticket.partner_email = ticket.partner_id.email or ticket.partner_email
                ticket.partner_phone = ticket.partner_id.phone or ticket.partner_phone

    def _compute_partner_ticket_count(self):
        partners = self.partner_id.commercial_partner_id
        counts = dict(self.with_context(active_test=False)._read_group(
            [('partner_id', 'child_of', partners.ids)], ['partner_id'], ['__count']))
        for ticket in self:
            commercial = ticket.partner_id.commercial_partner_id
            ticket.partner_ticket_count = sum(
                n for partner, n in counts.items() if partner.commercial_partner_id == commercial
            ) if commercial else 0

    @api.depends('assign_date')
    def _compute_assign_hours(self):
        for ticket in self:
            ticket.assign_hours = ticket._working_hours_since_creation(ticket.assign_date)

    @api.depends('close_date')
    def _compute_close_hours(self):
        for ticket in self:
            ticket.close_hours = ticket._working_hours_since_creation(ticket.close_date)

    @api.depends('sla_status_ids.deadline', 'sla_status_ids.reached_datetime', 'sla_status_ids.reached_late')
    def _compute_sla(self):
        for ticket in self:
            pending = ticket.sla_status_ids.filtered(lambda s: not s.reached_datetime)
            ticket.sla_deadline = min(pending.mapped('deadline')) if pending else False
            ticket.sla_reached_late = any(ticket.sla_status_ids.mapped('reached_late'))

    @api.depends('sla_deadline', 'sla_reached_late')
    def _compute_sla_fail(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.sla_fail = ticket.sla_reached_late or bool(ticket.sla_deadline and ticket.sla_deadline < now)
            ticket.sla_success = bool(ticket.sla_status_ids) and not ticket.sla_fail and not ticket.sla_deadline

    def _sla_fail_domain(self):
        return Domain('sla_reached_late', '=', True) | Domain('sla_deadline', '<', fields.Datetime.now())

    def _search_sla_fail(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        domain = self._sla_fail_domain() if True in value else Domain.FALSE
        if False in value:
            domain |= ~self._sla_fail_domain()
        return ~domain if operator == 'not in' else domain

    def _search_sla_success(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        success = (Domain('sla_status_ids', '!=', False) & Domain('sla_deadline', '=', False)
                   & Domain('sla_reached_late', '=', False))
        domain = success if True in value else Domain.FALSE
        if False in value:
            domain |= ~success
        return ~domain if operator == 'not in' else domain

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return stages.search(Domain('id', 'in', stages.ids) | Domain('team_ids', 'in', team_id))
        return stages

    def _get_working_calendar(self):
        self.ensure_one()
        return self.team_id.resource_calendar_id or self.company_id.resource_calendar_id

    def _working_hours_since_creation(self, end):
        self.ensure_one()
        if not (end and self.create_date):
            return 0.0
        calendar = self._get_working_calendar()
        if calendar:
            return calendar.get_work_hours_count(self.create_date, end, compute_leaves=True)
        return (end - self.create_date).total_seconds() / 3600

    @api.depends('ticket_ref')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = f'{ticket.name} (#{ticket.ticket_ref})' if ticket.ticket_ref else ticket.name

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = f'/my/tickets/{ticket.id}'

    # ------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        Partner = self.env['res.partner']
        for vals in vals_list:
            if not vals.get('ticket_ref'):
                vals['ticket_ref'] = self.env['ir.sequence'].sudo().next_by_code('helpdesk.ticket')
            vals['date_last_stage_update'] = now
            # set the stage here rather than leave it to the compute, so the stage's
            # email template (e.g. the acknowledgement on New) goes out on creation
            team_id = vals.get('team_id', self.env.context.get('default_team_id'))
            if team_id and not vals.get('stage_id'):
                stage = self.env['helpdesk.team'].browse(team_id).stage_ids[:1]
                if stage:
                    vals['stage_id'] = stage.id
            if vals.get('user_id'):
                vals['assign_date'] = now
            # A customer given only by email becomes a contact, so they can follow
            # the ticket and see it in the portal.
            if vals.get('partner_email') and not vals.get('partner_id'):
                email = tools.email_normalize(vals['partner_email'])
                if email:
                    partner = Partner.search([('email', '=ilike', email)], limit=1) or Partner.sudo().create({
                        'name': vals.get('partner_name') or email,
                        'email': email,
                        'phone': vals.get('partner_phone'),
                    })
                    vals['partner_id'] = partner.id
        tickets = super().create(vals_list)
        tickets.filtered(lambda t: t.fold).close_date = now
        tickets.filtered(lambda t: not t.user_id and t.team_id)._assign_from_team()
        for ticket in tickets.filtered('partner_id'):
            ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        tickets._sla_apply()
        tickets._send_rating_requests()
        return tickets

    def write(self, vals):
        now = fields.Datetime.now()
        if 'stage_id' in vals:
            vals['date_last_stage_update'] = now
            stage = self.env['helpdesk.stage'].browse(vals['stage_id'])
            if not stage.fold:
                vals['close_date'] = False
            if 'kanban_state' not in vals:
                vals['kanban_state'] = 'normal'
        if vals.get('user_id'):
            unassigned = self.filtered(lambda t: not t.assign_date)
        else:
            unassigned = self.browse()
        old_stages = {ticket: ticket.stage_id for ticket in self} if 'stage_id' in vals else {}
        res = super().write(vals)
        if unassigned:
            unassigned.sudo().assign_date = now
        if 'partner_id' in vals and vals['partner_id']:
            for ticket in self:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        if 'team_id' in vals:
            # a ticket moved to another team keeps its stage only if that team uses it,
            # and is assigned by its new team if nobody has it
            self.filtered(lambda t: not t.user_id and t.team_id)._assign_from_team()
        if SLA_FIELDS & vals.keys():
            self._sla_apply()
        if old_stages:
            changed = self.filtered(lambda t: t.stage_id != old_stages[t])
            changed.filtered(lambda t: t.fold and not t.close_date).sudo().close_date = now
            changed._sla_reach()
            changed._send_rating_requests()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=_('%s (copy)', ticket.name)) for ticket, vals in zip(self, vals_list)]

    # ------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------

    def _assign_from_team(self):
        # one by one, so round robin and balanced see the previous assignment
        for ticket in self:
            user = ticket.team_id._determine_user_to_assign()[ticket.team_id]
            if user:
                ticket.user_id = user

    def action_assign_to_me(self):
        self.user_id = self.env.user

    # ------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------

    def _sla_apply(self):
        """Attach the SLA policies that match each ticket and drop the ones that no
        longer do (policies already reached are kept as history)."""
        slas = self.env['helpdesk.sla'].search([('team_id', 'in', self.team_id.ids)])
        Status = self.env['helpdesk.sla.status'].sudo()
        to_remove = Status
        to_create = []
        for ticket in self:
            wanted = slas.filtered(lambda s: ticket.use_sla and s._applies_to(ticket))
            existing = ticket.sla_status_ids
            to_remove |= existing.filtered(lambda s: s.sla_id not in wanted and not s.reached_datetime)
            to_create += [{
                'ticket_id': ticket.id,
                'sla_id': sla.id,
                'deadline': Status._get_deadline(ticket, sla),
            } for sla in wanted - existing.sla_id]
        to_remove.unlink()
        if to_create:
            Status.create(to_create)
            self._sla_reach()

    def _sla_reach(self):
        """Mark SLAs reached once the ticket is at or past their target stage, and
        clear that again when a ticket goes back to an earlier stage."""
        now = fields.Datetime.now()
        for ticket in self:
            position = (ticket.stage_id.sequence, ticket.stage_id.id)
            for status in ticket.sla_status_ids.sudo():
                target = status.sla_stage_id
                reached = bool(ticket.stage_id) and position >= (target.sequence, target.id)
                if reached and not status.reached_datetime:
                    status.reached_datetime = now
                elif not reached and status.reached_datetime:
                    status.reached_datetime = False

    # ------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------

    def _track_template(self, changes):
        res = super()._track_template(changes)
        ticket = self[0]
        if 'stage_id' in changes and ticket.stage_id.template_id and ticket.partner_id:
            res['stage_id'] = (ticket.stage_id.template_id, {
                'auto_delete_keep_log': False,
                'subtype_id': self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'),
                'email_layout_xmlid': 'mail.mail_notification_light',
            })
        return res

    def _creation_subtype(self):
        return self.env.ref('helpdesk_management.mt_ticket_new')

    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'stage_id' in init_values:
            return self.env.ref('helpdesk_management.mt_ticket_stage')
        return super()._track_subtype(init_values)

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        if not msg_dict.get('author_id') and msg_dict.get('email_from'):
            author = self.env['mail.thread']._partner_find_from_emails_single(
                [msg_dict['email_from']], no_create=False)
            msg_dict['author_id'] = author.id
        values = {
            'name': msg_dict.get('subject') or _('No Subject'),
            'description': msg_dict.get('body'),
            'partner_id': msg_dict.get('author_id'),
        }
        if not values['partner_id']:
            name, email = tools.parse_contact_from_email(msg_dict.get('email_from') or '')
            values.update(partner_name=name, partner_email=email)
        values.update(custom_values or {})
        return super().message_new(msg_dict, custom_values=values)

    def _notify_get_reply_to(self, default=None, author_id=False):
        # replies go to the team's alias, so they land back on the ticket
        aliases = self.sudo().team_id._notify_get_reply_to(default=default, author_id=author_id)
        res = {ticket.id: aliases.get(ticket.team_id.id) for ticket in self}
        leftover = self.filtered(lambda t: not t.team_id)
        if leftover:
            res.update(super(HelpdeskTicket, leftover)._notify_get_reply_to(default=default, author_id=author_id))
        return res

    # ------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------

    def _send_rating_requests(self):
        for ticket in self:
            template = ticket.stage_id.rating_template_id
            if template and ticket.use_rating and ticket.partner_id and ticket.partner_id != self.env.user.partner_id:
                ticket.rating_send_request(template, lang=ticket.partner_id.lang, force_send=False)

    def _rating_get_parent_field_name(self):
        return 'team_id'

    def _rating_apply_get_default_subtype_id(self):
        return self.env['ir.model.data']._xmlid_to_res_id('helpdesk_management.mt_ticket_rated')

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_open_partner_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_ticket_action_main')
        action.update(
            domain=[('partner_id', 'child_of', self.partner_id.commercial_partner_id.id)],
            context={'default_partner_id': self.partner_id.id},
            name=_('Tickets of %s', self.partner_id.commercial_partner_id.name),
        )
        return action

    def action_open_ratings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_management.helpdesk_rating_action')
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        return action

    def _portal_closing_stage(self):
        """The stage a customer closing the ticket from the portal moves it to."""
        self.ensure_one()
        closing = self.team_id.stage_ids.filtered('fold')
        solved = self.env.ref('helpdesk_management.stage_solved', raise_if_not_found=False)
        return solved if solved in closing else closing[:1]

    def action_portal_close(self):
        for ticket in self:
            stage = ticket._portal_closing_stage()
            if not ticket.allow_portal_ticket_closing or not stage:
                raise UserError(_('This ticket cannot be closed from the portal.'))
            if not ticket.fold:
                ticket.stage_id = stage
                user = self.env.user
                ticket.message_post(
                    body=_('The customer closed the ticket.'),
                    subtype_xmlid='mail.mt_note',
                    author_id=(ticket.partner_id if user._is_public() else user.partner_id).id,
                )

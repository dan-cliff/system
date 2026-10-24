import logging
from datetime import timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import html2plaintext

from .helpdesk_ai import ai_credentials, ai_provider_label, ai_request_json

_logger = logging.getLogger(__name__)

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

# Products offered to the AI by name, so it can pick the ones a ticket is about.
AI_PRODUCT_LIMIT = 200


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

    def _default_source_id(self):
        # tickets logged in the backend; email, website form and Help Centre set their own
        return self.env.ref('helpdesk_management.ticket_source_direct', raise_if_not_found=False)

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
        'res.users', string='Agent', tracking=True, index=True,
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
    product_ids = fields.Many2many('product.product', string='Products', tracking=True)
    source_id = fields.Many2one(
        'helpdesk.ticket.source', string='Source', tracking=True, index=True, ondelete='restrict',
        default=_default_source_id, help='How the ticket came in.')
    date_raised = fields.Datetime(
        'Date Raised', required=True, default=fields.Datetime.now, tracking=True, index=True, copy=False,
        help='When the customer raised the ticket (for emails: when the email was sent).')
    days_open = fields.Float(
        'Days Open', compute='_compute_days', store=True, digits=(16, 1), aggregator='avg',
        help='Days from being raised until closed, or until today while the ticket is open.')
    days_to_resolution = fields.Float(
        'Days to Resolution', compute='_compute_days', store=True, digits=(16, 1), aggregator='avg',
        help='Days from being raised until closed; 0 while the ticket is open, so filter on '
             'closed tickets when averaging it.')
    sentiment_id = fields.Many2one(
        'helpdesk.sentiment', string='Customer Sentiment', tracking=True, index=True, ondelete='restrict',
        help='How the customer feels, judged from the tone of the ticket (estimated by AI when it is set up).')
    sentiment_score = fields.Integer(
        related='sentiment_id.score', store=True, aggregator='avg', string='Sentiment Score')
    sentiment_reason = fields.Text('Sentiment Notes', help='Why the AI judged the sentiment as it did.')
    ai_recommended_actions = fields.Html('Recommended Actions', copy=False)
    ai_state = fields.Selection([
        ('pending', 'Queued'),
        ('done', 'Analysed'),
        ('failed', 'Failed'),
    ], string='AI Analysis', copy=False, readonly=True, index=True)
    ai_date = fields.Datetime('AI Analysed On', copy=False, readonly=True)
    ai_error = fields.Char('AI Error', copy=False, readonly=True)
    ai_available = fields.Boolean(compute='_compute_ai_available')
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

    @api.depends('date_raised', 'close_date')
    def _compute_days(self):
        now = fields.Datetime.now()
        for ticket in self:
            if not ticket.date_raised:
                ticket.days_open = ticket.days_to_resolution = 0.0
                continue
            end = ticket.close_date or now
            ticket.days_open = max((end - ticket.date_raised).total_seconds(), 0) / 86400
            ticket.days_to_resolution = (
                max((ticket.close_date - ticket.date_raised).total_seconds(), 0) / 86400
                if ticket.close_date else 0.0
            )

    def _compute_ai_available(self):
        available = bool(ai_credentials(self.env)[1])
        for ticket in self:
            ticket.ai_available = available

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
        # sudo: users with "Create Only" can't edit what they have just created
        tickets.filtered(lambda t: t.fold).sudo().close_date = now
        tickets.filtered(lambda t: not t.user_id and t.team_id)._assign_from_team()
        for ticket in tickets.filtered('partner_id'):
            ticket.sudo().message_subscribe(partner_ids=ticket.partner_id.ids)
        tickets._sla_apply()
        tickets._send_rating_requests()
        tickets._ai_queue()
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
                ticket.sudo().user_id = user

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
        source = self.env.ref('helpdesk_management.ticket_source_email', raise_if_not_found=False)
        if source:
            values['source_id'] = source.id
        if msg_dict.get('date'):
            # the sender's clock decides the date; never later than its arrival
            values['date_raised'] = min(fields.Datetime.to_datetime(msg_dict['date']), fields.Datetime.now())
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

    # ------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------

    @api.model
    def _cron_refresh_days_open(self):
        """Days Open of open tickets grows every day: recompute it nightly."""
        tickets = self.search([('fold', '=', False)])
        self.env.add_to_compute(self._fields['days_open'], tickets)
        tickets._recompute_recordset(['days_open'])

    # ------------------------------------------------------------
    # AI triage
    # ------------------------------------------------------------

    def _ai_queue(self):
        """Queue new tickets for AI triage in the background (only when an AI key is set),
        so creating a ticket never waits on the AI."""
        if not self or not ai_credentials(self.env)[1]:
            return
        self.sudo().write({'ai_state': 'pending'})
        cron = self.env.ref('helpdesk_management.ir_cron_helpdesk_ai_triage', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_ai_triage(self):
        if not ai_credentials(self.env)[1]:
            return
        tickets = self.search([('ai_state', '=', 'pending')], order='id')
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(tickets))
        for ticket in tickets:
            ticket._ai_analyse_safe()
            # commits each ticket; stops when the run is out of time (the rest go next run)
            if not Cron._commit_progress(1):
                break

    def _ai_analyse_safe(self):
        """Run the AI triage, recording a failure on the ticket rather than raising."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self._ai_analyse()
        except Exception as exc:  # noqa: BLE001 - any failure is kept on the ticket for the user
            _logger.warning('Helpdesk AI triage failed for ticket %s: %s', self.id, exc)
            self.sudo().write({'ai_state': 'failed', 'ai_error': str(exc)[:500]})

    def _ai_missing_fields(self):
        """Labels of the fields the AI will fill in on this ticket because they are empty."""
        self.ensure_one()
        missing = []
        if not self.team_id:
            missing.append(self._fields['team_id'].get_description(self.env)['string'])
        if not self.ticket_type_id:
            missing.append(self._fields['ticket_type_id'].get_description(self.env)['string'])
        if not self.product_ids:
            missing.append(self._fields['product_ids'].get_description(self.env)['string'])
        if not self.tag_ids:
            missing.append(self._fields['tag_ids'].get_description(self.env)['string'])
        if self.priority == '0':
            missing.append(self._fields['priority'].get_description(self.env)['string'])
        return missing

    def get_ai_job_info(self):
        """What the AI is about to do, worded for the progress overlay."""
        self.ensure_one()
        self.check_access('write')
        return {
            'provider': ai_provider_label(self.env),
            'missing': self._ai_missing_fields(),
        }

    def action_ai_analyse(self):
        """Explicit "Analyse with AI" (run from the form behind the progress overlay)."""
        if not ai_credentials(self.env)[1]:
            raise UserError(_('No AI is set up. Add a Claude AI or Google Gemini API key in '
                              'Settings > General Settings > Integrations.'))
        self.check_access('write')
        for ticket in self:
            ticket._ai_analyse()
        return True

    def _ai_prompt(self):
        self.ensure_one()
        env = self.env
        teams = env['helpdesk.team'].sudo().search([('company_id', 'in', [self.company_id.id, False])])
        types = env['helpdesk.ticket.type'].sudo().search([])
        tags = env['helpdesk.tag'].sudo().search([])
        sentiments = env['helpdesk.sentiment'].sudo().search([])
        products = env['product.product'].sudo().search(
            [('sale_ok', '=', True), ('company_id', 'in', [self.company_id.id, False])],
            limit=AI_PRODUCT_LIMIT, order='name')
        priorities = [label for _value, label in TICKET_PRIORITY]

        def names(records):
            return ', '.join(f'"{name}"' for name in records.mapped('display_name')) or '(none)'

        description = html2plaintext(self.description or '').strip()
        lines = [
            'A customer support ticket follows. Triage it.',
            '',
            f'Subject: {self.name}',
            f'Customer: {self.partner_id.display_name or self.partner_name or "(unknown)"}',
            f'Customer email: {self.partner_email or "(unknown)"}',
            f'Source: {self.source_id.name or "(unknown)"}',
            'Description:',
            description[:12000] or '(no description)',
        ]
        # the customer's later emails on the ticket also show their tone
        messages = self.message_ids.filtered(
            lambda m: m.message_type in ('email', 'comment') and m.author_id
            and m.author_id == self.partner_id and m.body)[:5]
        if messages:
            lines += ['', 'Messages from the customer (newest first):']
            lines += ['- ' + html2plaintext(m.body).strip()[:2000] for m in messages]
        lines += [
            '',
            'Choose only from these lists (copy names exactly; use null or [] when nothing fits):',
            f'Teams: {names(teams)}',
            f'Ticket types: {names(types)}',
            f'Tags: {names(tags)}',
            f'Priorities: {", ".join(chr(34) + p + chr(34) for p in priorities)}',
            f'Customer sentiments (most positive first): {names(sentiments)}',
            f'Products: {names(products)}',
            '',
            'Answer with ONLY a JSON object, no other text:',
            '{',
            '  "team": "<team name or null>",',
            '  "ticket_type": "<ticket type or null>",',
            '  "tags": ["<tag>", ...],',
            '  "priority": "<priority>",',
            '  "products": ["<product>", ...],',
            '  "sentiment": "<customer sentiment>",',
            '  "sentiment_reason": "<one or two sentences on the tone that led to the sentiment>",',
            '  "recommended_actions": ["<a concrete next step for the support agent>", ...]',
            '}',
            'Judge the sentiment from the tone of the customer\'s words. Give 2 to 5 recommended '
            'actions, most important first, that would resolve the issue and restore the customer\'s '
            'confidence.',
        ]
        return '\n'.join(lines)

    @staticmethod
    def _ai_match(records, name):
        """The record in `records` named `name` (case-insensitive), or an empty recordset."""
        if not isinstance(name, str) or not name.strip():
            return records.browse()
        wanted = name.strip().lower()
        return records.filtered(lambda r: (r.display_name or '').lower() == wanted)[:1] \
            or records.filtered(lambda r: (r.name or '').lower() == wanted)[:1]

    def _ai_analyse(self):
        """Send the ticket to the AI, fill in what is missing, estimate the customer
        sentiment and store the recommended corrective actions."""
        self.ensure_one()
        system = ('You are an experienced customer support lead triaging helpdesk tickets. '
                  'You answer with JSON only.')
        data = ai_request_json(self.env, self._ai_prompt(), system=system)
        ticket = self.sudo()
        env = ticket.env
        vals = {}

        def as_list(value):
            return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

        if not ticket.team_id:
            team = self._ai_match(env['helpdesk.team'].search([('company_id', 'in', [ticket.company_id.id, False])]),
                                  data.get('team'))
            if team:
                vals['team_id'] = team.id
        if not ticket.ticket_type_id:
            ticket_type = self._ai_match(env['helpdesk.ticket.type'].search([]), data.get('ticket_type'))
            if ticket_type:
                vals['ticket_type_id'] = ticket_type.id
        if not ticket.tag_ids:
            all_tags = env['helpdesk.tag'].search([])
            tags = env['helpdesk.tag'].union(*(self._ai_match(all_tags, n) for n in as_list(data.get('tags'))))
            if tags:
                vals['tag_ids'] = [(6, 0, tags.ids)]
        if ticket.priority == '0':
            priority = {label.lower(): value for value, label in TICKET_PRIORITY}.get(
                str(data.get('priority') or '').strip().lower())
            if priority and priority != '0':
                vals['priority'] = priority
        if not ticket.product_ids:
            Product = env['product.product']
            products = Product
            for name in as_list(data.get('products')):
                products |= Product.search(
                    [('name', '=ilike', name.strip()), ('company_id', 'in', [ticket.company_id.id, False])], limit=1)
            if products:
                vals['product_ids'] = [(6, 0, products.ids)]
        sentiment = self._ai_match(env['helpdesk.sentiment'].search([]), data.get('sentiment'))
        if sentiment:
            vals['sentiment_id'] = sentiment.id
        if isinstance(data.get('sentiment_reason'), str):
            vals['sentiment_reason'] = data['sentiment_reason'].strip()
        actions = as_list(data.get('recommended_actions'))
        if actions:
            vals['ai_recommended_actions'] = '<ol>%s</ol>' % ''.join(
                '<li>%s</li>' % tools.html_escape(action.strip()) for action in actions if action.strip())
        vals.update(ai_state='done', ai_date=fields.Datetime.now(), ai_error=False)
        ticket.write(vals)
        return True

    # ------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------

    @api.model
    def get_dashboard_data(self):
        """Numbers and sentiment series for the Helpdesk dashboard, as the current user sees them."""
        open_domain = Domain('fold', '=', False)
        by_company = [
            {'id': company.id, 'name': company.name, 'count': count}
            for company, count in self._read_group(open_domain, ['company_id'], ['__count'],
                                                   order='__count desc')
        ]
        by_team = [
            {'id': team.id or False, 'name': team.name or _('No Team'), 'count': count}
            for team, count in self._read_group(open_domain, ['team_id'], ['__count'], order='__count desc')
        ]
        mine = Domain('user_id', '=', self.env.uid)
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        return {
            'uid': self.env.uid,
            'my_open_count': self.search_count(open_domain & mine),
            'open_count': self.search_count(open_domain),
            'by_company': by_company,
            'by_team': by_team,
            'multi_company': len(by_company) > 1 or self.env.user.has_group('base.group_multi_company'),
            'sentiments': [
                {'score': s.score, 'name': s.name}
                for s in self.env['helpdesk.sentiment'].search([])
            ],
            'charts': {
                'last_12_months': self._sentiment_series(
                    mine, month_start - relativedelta(months=11), today, 'month'),
                'year_to_date': self._sentiment_series(mine, today.replace(month=1, day=1), today, 'month'),
                'last_30_days': self._sentiment_series(mine, today - timedelta(days=29), today, 'day'),
            },
        }

    def _sentiment_series(self, domain, start, end, interval):
        """Average sentiment score of the tickets in `domain` raised from `start` to
        `end` (dates, inclusive), one point per `interval` ('month' or 'day')."""
        tz_start = self._date_to_utc(start)
        tz_end = self._date_to_utc(end + timedelta(days=1))
        domain = (Domain(domain) & Domain('sentiment_id', '!=', False)
                  & Domain('date_raised', '>=', tz_start) & Domain('date_raised', '<', tz_end))
        groups = self._read_group(domain, [f'date_raised:{interval}'], ['sentiment_score:avg', '__count'])
        values = {}
        for bucket, average, count in groups:
            key = (bucket.date() if hasattr(bucket, 'date') else bucket)
            key = key.replace(day=1) if interval == 'month' else key
            values[key] = (average, count)
        labels, points, counts = [], [], []
        current = start.replace(day=1) if interval == 'month' else start
        step = relativedelta(months=1) if interval == 'month' else timedelta(days=1)
        while current <= end:
            average, count = values.get(current, (None, 0))
            labels.append(current.strftime('%m/%Y') if interval == 'month' else current.strftime('%d/%m/%Y'))
            points.append(round(average, 2) if average is not None else None)
            counts.append(count)
            current += step
        total = sum(counts)
        overall = (sum(p * c for p, c in zip(points, counts) if p is not None) / total) if total else None
        return {
            'labels': labels,
            'values': points,
            'counts': counts,
            'average': round(overall, 2) if overall is not None else None,
            'ticket_count': total,
        }

    def _date_to_utc(self, day):
        """Midnight of `day` in the user's timezone, as a naive UTC datetime."""
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        local = tz.localize(fields.Datetime.to_datetime(day))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

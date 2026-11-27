"""Agile planning, like Jira Scrum: sprints and epics.

A sprint is a time-box of work (Planned, Active, Completed). Starting it records
the committed scope; completing it records what was done (the velocity) and moves
the unfinished tickets on to another sprint or back to the backlog. A ticket keeps
every sprint it has been in, so long-running work is tracked across sprints.

An epic is a large body of work: its tickets and features belong to it, and it
tracks the sprints that worked on it (a ticket's sprints are added to its epic).
"""
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .dev_release import first_monday

SPRINT_STATES = [
    ('planned', 'Planned'),
    ('active', 'Active'),
    ('closed', 'Completed'),
]


class DevSprint(models.Model):
    _name = 'dev.sprint'
    _description = 'Sprint'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(tracking=True, copy=False,
                       help='Left empty, it is set to Sprint YYYY-NNN: the NNNth sprint starting in that year.')
    goal = fields.Text('Sprint Goal', tracking=True, help='What the team commits to achieving in this sprint.')
    state = fields.Selection(SPRINT_STATES, 'Status', default='planned', required=True, tracking=True, copy=False,
                             index=True, group_expand=True)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    user_id = fields.Many2one('res.users', 'Scrum Master', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    release_id = fields.Many2one('dev.release', 'Release', tracking=True, index='btree_not_null',
                                 help='The release this sprint\'s work ships in.')
    repository_id = fields.Many2one('dev.repository', 'Repository', related='release_id.repository_id', store=True)
    date_start = fields.Date('Start Date', required=True, tracking=True,
                             default=lambda self: first_monday(fields.Date.context_today(self)))
    date_end = fields.Date('End Date', compute='_compute_date_end', store=True, readonly=False, tracking=True)
    capacity_points = fields.Float('Capacity', help='Story points the team expects to complete in this sprint.')

    ticket_ids = fields.Many2many('dev.ticket', 'dev_sprint_ticket_rel', 'sprint_id', 'ticket_id', string='Tickets')
    epic_ids = fields.Many2many('dev.epic', 'dev_epic_sprint_rel', 'sprint_id', 'epic_id', string='Epics')

    # Sprint report: recorded when the sprint starts and when it completes.
    date_started = fields.Datetime('Started On', readonly=True, copy=False)
    date_completed = fields.Datetime('Completed On', readonly=True, copy=False)
    committed_ticket_ids = fields.Many2many('dev.ticket', 'dev_sprint_committed_ticket_rel', 'sprint_id', 'ticket_id',
                                            string='Committed Tickets', readonly=True, copy=False,
                                            help='The tickets in the sprint when it started.')
    committed_points = fields.Float('Committed Points', readonly=True, copy=False,
                                    help='Story points in the sprint when it started.')
    completed_ticket_ids = fields.Many2many('dev.ticket', 'dev_sprint_completed_ticket_rel', 'sprint_id', 'ticket_id',
                                            string='Completed Tickets', readonly=True, copy=False,
                                            help='The tickets done when the sprint completed.')
    completed_points = fields.Float('Velocity', readonly=True, copy=False,
                                    help='Story points completed in the sprint.')
    carried_over_ticket_ids = fields.Many2many('dev.ticket', 'dev_sprint_carried_ticket_rel', 'sprint_id',
                                               'ticket_id', string='Not Completed', readonly=True, copy=False,
                                               help='The tickets still open when the sprint completed.')
    next_sprint_id = fields.Many2one('dev.sprint', 'Carried Over To', readonly=True, copy=False)
    added_ticket_ids = fields.Many2many('dev.ticket', compute='_compute_added_ticket_ids', string='Added After Start',
                                        help='Scope change: tickets added once the sprint had started.')

    ticket_count = fields.Integer('Ticket Count', compute='_compute_progress')
    ticket_done_count = fields.Integer('Tickets Done', compute='_compute_progress')
    points_total = fields.Float('Story Points', compute='_compute_progress')
    points_done = fields.Float('Points Done', compute='_compute_progress')
    progress = fields.Float('Progress (%)', compute='_compute_progress')
    days_left = fields.Integer('Days Left', compute='_compute_days_left')
    burndown = fields.Html('Burndown', compute='_compute_burndown', sanitize=False)

    @api.depends('date_start')
    def _compute_date_end(self):
        days = self.env['dev.release']._days('sprint_days')
        for sprint in self:
            sprint.date_end = sprint.date_start and sprint.date_start + timedelta(days=max(days - 1, 0))

    @api.depends('ticket_ids.is_closed', 'ticket_ids.story_points')
    def _compute_progress(self):
        for sprint in self:
            tickets = sprint.ticket_ids
            done = tickets.filtered('is_closed')
            sprint.ticket_count = len(tickets)
            sprint.ticket_done_count = len(done)
            sprint.points_total = sum(tickets.mapped('story_points'))
            sprint.points_done = sum(done.mapped('story_points'))
            if sprint.points_total:
                sprint.progress = 100.0 * sprint.points_done / sprint.points_total
            else:
                sprint.progress = 100.0 * len(done) / len(tickets) if tickets else 0.0

    @api.depends('ticket_ids', 'committed_ticket_ids', 'state')
    def _compute_added_ticket_ids(self):
        for sprint in self:
            sprint.added_ticket_ids = (sprint.ticket_ids - sprint.committed_ticket_ids
                                       if sprint.state != 'planned' else False)

    @api.depends('date_end', 'state')
    def _compute_days_left(self):
        today = fields.Date.context_today(self)
        for sprint in self:
            sprint.days_left = max((sprint.date_end - today).days + 1, 0) if sprint.date_end and \
                sprint.state == 'active' else 0

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for sprint in self:
            if sprint.date_start and sprint.date_end and sprint.date_end < sprint.date_start:
                raise UserError(_('The sprint must end on or after its start date.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self._next_name(vals.get('date_start') or self._fields['date_start'].default(self))
        sprints = super().create(vals_list)
        sprints.ticket_ids._link_epic_sprints()
        return sprints

    @api.model
    def _next_name(self, date_start):
        """Sprint YYYY-NNN: numbered within the year the sprint starts in (the sequence restarts each year)."""
        return self.env['ir.sequence'].sudo().next_by_code(
            'dev.sprint', sequence_date=fields.Date.to_date(date_start)) or _('New Sprint')

    def write(self, vals):
        result = super().write(vals)
        if 'ticket_ids' in vals:
            self.ticket_ids._link_epic_sprints()
        return result

    # ── Burndown ───────────────────────────────────────────────────────────
    def _burndown_series(self):
        """(days, ideal, actual) of the sprint: remaining story points (or tickets) at the end of each day.

        ``actual`` stops at today. Tickets closed before the sprint started count as done.
        """
        self.ensure_one()
        if not self.date_start or not self.date_end:
            return [], [], []
        tickets = self.ticket_ids
        use_points = any(tickets.mapped('story_points'))

        def weight(ticket):
            return ticket.story_points if use_points else 1.0

        total = sum(weight(t) for t in tickets)
        days = [self.date_start + timedelta(days=i) for i in range((self.date_end - self.date_start).days + 1)]
        span = max(len(days) - 1, 1)
        ideal = [total * (1 - i / span) for i in range(len(days))]
        today = fields.Date.context_today(self)
        actual = []
        for day in days:
            if day > today:
                break
            done = sum(weight(t) for t in tickets
                       if t.is_closed and t.date_closed and fields.Date.context_today(self, t.date_closed) <= day)
            actual.append(total - done)
        return days, ideal, actual

    @api.depends('ticket_ids.is_closed', 'ticket_ids.date_closed', 'ticket_ids.story_points', 'date_start', 'date_end')
    def _compute_burndown(self):
        for sprint in self:
            sprint.burndown = sprint._burndown_svg()

    def _burndown_svg(self):
        days, ideal, actual = self._burndown_series()
        if not days:
            return False
        width, height, pad = 640, 240, 36
        top = max(ideal + actual + [1.0])
        span = max(len(days) - 1, 1)

        def point(i, value):
            return '%.1f,%.1f' % (pad + (width - 2 * pad) * i / span, height - pad - (height - 2 * pad) * value / top)

        ideal_line = ' '.join(point(i, v) for i, v in enumerate(ideal))
        actual_line = ' '.join(point(i, v) for i, v in enumerate(actual))
        labels = Markup('').join(
            Markup('<text x="%s" y="%s" font-size="10" text-anchor="middle" fill="#6c757d">%s</text>') % (
                pad + (width - 2 * pad) * i / span, height - pad + 16, day.strftime('%d/%m'))
            for i, day in enumerate(days) if i in (0, len(days) - 1) or (len(days) <= 15 and i % 2 == 0))
        return Markup(
            '<svg viewBox="0 0 %(w)s %(h)s" width="100%%" style="max-width:%(w)spx" role="img" aria-label="%(aria)s">'
            '<line x1="%(p)s" y1="%(b)s" x2="%(r)s" y2="%(b)s" stroke="#A9ABDC"/>'
            '<line x1="%(p)s" y1="%(p)s" x2="%(p)s" y2="%(b)s" stroke="#A9ABDC"/>'
            '<text x="%(lx)s" y="%(ly)s" font-size="10" text-anchor="end" fill="#6c757d">%(top)s</text>'
            '<polyline points="%(ideal)s" fill="none" stroke="#A9ABDC" stroke-width="2" stroke-dasharray="6 4"/>'
            '<polyline points="%(actual)s" fill="none" stroke="#8E5CF0" stroke-width="3"/>'
            '%(labels)s'
            '<text x="%(r)s" y="14" font-size="11" text-anchor="end" fill="#8E5CF0">%(remaining)s</text>'
            '<text x="%(r)s" y="28" font-size="11" text-anchor="end" fill="#A9ABDC">%(guide)s</text>'
            '</svg>') % {
            'w': width, 'h': height, 'p': pad, 'b': height - pad, 'r': width - pad, 'lx': pad - 4, 'ly': pad + 4,
            'top': '%g' % top, 'ideal': ideal_line, 'actual': actual_line, 'labels': labels,
            'remaining': _('Remaining'), 'guide': _('Guideline'), 'aria': _('Sprint burndown chart'),
        }

    # ── Workflow ───────────────────────────────────────────────────────────
    def action_start(self):
        """Start the sprint, recording the committed scope."""
        for sprint in self:
            if sprint.state != 'planned':
                raise UserError(_('Only a planned sprint can be started.'))
            if not sprint.ticket_ids:
                raise UserError(_('Add tickets to %s before starting it.', sprint.name))
            sprint.write({
                'state': 'active',
                'date_started': fields.Datetime.now(),
                'committed_ticket_ids': [(6, 0, sprint.ticket_ids.ids)],
                'committed_points': sum(sprint.ticket_ids.mapped('story_points')),
            })
            sprint.message_post(body=_('Sprint started with %(count)s ticket(s), %(points)s story points committed.',
                                       count=len(sprint.ticket_ids), points='%g' % sprint.committed_points))
        return True

    def action_complete(self):
        """Complete the sprint; when tickets are unfinished, ask where they go."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Only an active sprint can be completed.'))
        if not self.ticket_ids.filtered(lambda t: not t.is_closed):
            self._complete()
            return True
        return {
            'type': 'ir.actions.act_window',
            'name': _('Complete %s', self.name),
            'res_model': 'dev.sprint.complete',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sprint_id': self.id},
        }

    def _complete(self, target=None):
        """Record the sprint report and move unfinished tickets to ``target`` (another sprint) or the backlog.

        Unfinished tickets stay linked to this sprint too, so their history across sprints is kept.
        """
        self.ensure_one()
        done = self.ticket_ids.filtered('is_closed')
        unfinished = self.ticket_ids - done
        if target:
            if target == self or target.state == 'closed':
                raise UserError(_('Move the unfinished tickets to a planned or active sprint.'))
            unfinished.write({'sprint_ids': [(4, target.id)]})
        self.write({
            'state': 'closed',
            'date_completed': fields.Datetime.now(),
            'completed_ticket_ids': [(6, 0, done.ids)],
            'completed_points': sum(done.mapped('story_points')),
            'carried_over_ticket_ids': [(6, 0, unfinished.ids)],
            'next_sprint_id': target.id if target else False,
        })
        destination = target.name if target else _('the backlog')
        self.message_post(body=_('Sprint completed: %(done)s ticket(s) done (%(points)s points); %(open)s unfinished '
                                 'ticket(s) moved to %(to)s.', done=len(done), points='%g' % self.completed_points,
                                 open=len(unfinished), to=destination))
        return True

    def _next_planned_sprint(self):
        self.ensure_one()
        return self.search([('state', '=', 'planned'), ('id', '!=', self.id), ('company_id', '=', self.company_id.id),
                            ('date_start', '>=', self.date_start)], order='date_start, id', limit=1)

    def _create_next_sprint(self):
        self.ensure_one()
        start = self.date_end + timedelta(days=1) if self.date_end else first_monday(fields.Date.context_today(self))
        return self.create({
            'date_start': start,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'release_id': self.release_id.id,
            'capacity_points': self.capacity_points,
        })

    def action_reset_planned(self):
        self.filtered(lambda s: s.state == 'active').write({
            'state': 'planned', 'date_started': False, 'committed_ticket_ids': [(5, 0, 0)], 'committed_points': 0.0})
        return True

    def action_open_board(self):
        """The sprint's board: its tickets by stage."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(name=self.name, domain=[('sprint_ids', 'in', self.id)],
                      context={'default_sprint_ids': [(4, self.id)]})
        return action

    def action_open_epics(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_epic_action')
        action.update(domain=[('id', 'in', self.epic_ids.ids)])
        return action


class DevEpic(models.Model):
    _name = 'dev.epic'
    _description = 'Epic'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority_sequence, sequence, id desc'
    _rec_names_search = ['name', 'key']

    key = fields.Char('Epic Number', readonly=True, copy=False, index=True)
    name = fields.Char('Title', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color', help='Shown on the tickets of the epic.')
    summary = fields.Text(help='What this epic delivers, in a sentence or two.')
    description = fields.Html()
    stage_id = fields.Many2one('dev.epic.stage', 'Stage', tracking=True, index=True, copy=False, ondelete='restrict',
                               default=lambda self: self.env['dev.epic.stage'].search([], limit=1),
                               group_expand='_read_group_stage_ids')
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True)
    priority_id = fields.Many2one('dev.priority', 'Priority', tracking=True,
                                  default=lambda self: self.env['dev.priority'].search([], offset=2, limit=1))
    priority_sequence = fields.Integer('Priority Order', related='priority_id.sequence', store=True)
    user_id = fields.Many2one('res.users', 'Owner', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    tag_ids = fields.Many2many('dev.tag', 'dev_epic_tag_rel', 'epic_id', 'tag_id', string='Labels')
    date_start = fields.Date('Start Date', tracking=True)
    date_target = fields.Date('Target Date', tracking=True)

    ticket_ids = fields.One2many('dev.ticket', 'epic_id', string='Tickets')
    feature_ids = fields.One2many('dev.feature', 'epic_id', string='Features')
    sprint_ids = fields.Many2many('dev.sprint', 'dev_epic_sprint_rel', 'epic_id', 'sprint_id', string='Sprints',
                                  help='Sprints that worked on this epic (its tickets\' sprints are added for you).')
    release_ids = fields.Many2many('dev.release', compute='_compute_release_ids', string='Releases')
    ticket_count = fields.Integer('Ticket Count', compute='_compute_progress')
    ticket_done_count = fields.Integer('Tickets Done', compute='_compute_progress')
    points_total = fields.Float('Story Points', compute='_compute_progress')
    points_done = fields.Float('Points Done', compute='_compute_progress')
    progress = fields.Float('Progress (%)', compute='_compute_progress')
    sprint_count = fields.Integer('Sprint Count', compute='_compute_sprint_count')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order=stages._order)

    @api.depends('ticket_ids.is_closed', 'ticket_ids.story_points')
    def _compute_progress(self):
        for epic in self:
            tickets = epic.ticket_ids
            done = tickets.filtered('is_closed')
            epic.ticket_count = len(tickets)
            epic.ticket_done_count = len(done)
            epic.points_total = sum(tickets.mapped('story_points'))
            epic.points_done = sum(done.mapped('story_points'))
            if epic.points_total:
                epic.progress = 100.0 * epic.points_done / epic.points_total
            else:
                epic.progress = 100.0 * len(done) / len(tickets) if tickets else 0.0

    @api.depends('ticket_ids.release_id', 'feature_ids.release_id')
    def _compute_release_ids(self):
        for epic in self:
            epic.release_ids = epic.ticket_ids.release_id | epic.feature_ids.release_id

    @api.depends('sprint_ids')
    def _compute_sprint_count(self):
        for epic in self:
            epic.sprint_count = len(epic.sprint_ids)

    @api.depends('name', 'key')
    def _compute_display_name(self):
        for epic in self:
            epic.display_name = '%s %s' % (epic.key, epic.name) if epic.key else epic.name

    @api.constrains('date_start', 'date_target')
    def _check_dates(self):
        for epic in self:
            if epic.date_start and epic.date_target and epic.date_target < epic.date_start:
                raise UserError(_('The target date must be on or after the start date.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = self.env['ir.sequence'].sudo().next_by_code('dev.epic') or False
        return super().create(vals_list)

    def action_open_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(name=self.display_name, domain=[('epic_id', '=', self.id)],
                      context={'default_epic_id': self.id})
        return action

    def action_open_sprints(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_sprint_action')
        action.update(domain=[('id', 'in', self.sprint_ids.ids)], context={})
        return action


class DevSprintComplete(models.TransientModel):
    _name = 'dev.sprint.complete'
    _description = 'Complete Sprint'

    sprint_id = fields.Many2one('dev.sprint', required=True, readonly=True)
    done_count = fields.Integer('Done', compute='_compute_counts')
    open_count = fields.Integer('Unfinished', compute='_compute_counts')
    create_next = fields.Boolean('Create the next sprint',
                                 help='Create a new sprint, starting the day after this one ends, for the unfinished '
                                      'tickets.')
    target_sprint_id = fields.Many2one('dev.sprint', 'Move Unfinished Tickets To',
                                       domain="[('state', '!=', 'closed'), ('id', '!=', sprint_id)]",
                                       help='Leave empty to send them back to the backlog.')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        sprint = self.env['dev.sprint'].browse(values.get('sprint_id'))
        if sprint and 'target_sprint_id' in fields_list:
            values['target_sprint_id'] = sprint._next_planned_sprint().id
            values['create_next'] = not values['target_sprint_id']
        return values

    @api.depends('sprint_id')
    def _compute_counts(self):
        for wizard in self:
            tickets = wizard.sprint_id.ticket_ids
            wizard.done_count = len(tickets.filtered('is_closed'))
            wizard.open_count = len(tickets) - wizard.done_count

    def action_complete(self):
        self.ensure_one()
        target = self.target_sprint_id
        if self.create_next and not target:
            target = self.sprint_id._create_next_sprint()
        self.sprint_id._complete(target or None)
        if target:
            return {'type': 'ir.actions.act_window', 'res_model': 'dev.sprint', 'res_id': target.id,
                    'view_mode': 'form'}
        return {'type': 'ir.actions.act_window_close'}


class DevTicketAddSprint(models.TransientModel):
    _name = 'dev.ticket.add.sprint'
    _description = 'Add Tickets to a Sprint'

    sprint_id = fields.Many2one('dev.sprint', 'Sprint', required=True, domain="[('state', '!=', 'closed')]")
    ticket_ids = fields.Many2many('dev.ticket', string='Tickets',
                                  default=lambda self: self.env.context.get('active_ids'))

    def action_add(self):
        self.ensure_one()
        self.ticket_ids.write({'sprint_ids': [(4, self.sprint_id.id)]})
        return {'type': 'ir.actions.act_window_close'}

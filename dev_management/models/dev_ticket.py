"""Development tickets (stories, tasks, bugs, ...), like Jira issues.

Tickets move across a board of configurable stages, can have sub-tasks, can be
linked to each other (blocks / relates to / duplicates, ...), belong to a
feature and a release, and list the GitHub branches where they are worked on.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext


class DevTicket(models.Model):
    _name = 'dev.ticket'
    _description = 'Development Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dev.ai.mixin']
    _order = 'priority_sequence, sequence, id desc'
    _rec_names_search = ['name', 'key']
    _dev_ai_jobs = ('ticket_criteria',)

    key = fields.Char('Ticket Number', readonly=True, copy=False, index=True)
    name = fields.Char('Summary', required=True, tracking=True)
    description = fields.Html()
    sequence = fields.Integer(default=10, help='Order in the backlog.')
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    type_id = fields.Many2one('dev.ticket.type', 'Type', tracking=True,
                              default=lambda self: self.env['dev.ticket.type'].search([], limit=1))
    type_icon = fields.Char('Type Icon', related='type_id.icon')
    priority_id = fields.Many2one('dev.priority', 'Priority', tracking=True,
                                  default=lambda self: self.env['dev.priority'].search([], offset=2, limit=1))
    priority_sequence = fields.Integer('Priority Order', related='priority_id.sequence', store=True)
    stage_id = fields.Many2one('dev.ticket.stage', 'Stage', tracking=True, index=True, copy=False,
                               default=lambda self: self.env['dev.ticket.stage'].search([], limit=1),
                               group_expand='_read_group_stage_ids', ondelete='restrict')
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Ready for Next Stage'),
    ], 'Status', default='normal', copy=False, tracking=True)
    user_id = fields.Many2one('res.users', 'Assignee', tracking=True, domain=[('share', '=', False)])
    reporter_id = fields.Many2one('res.users', 'Reporter', default=lambda self: self.env.user,
                                  domain=[('share', '=', False)])
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    tag_ids = fields.Many2many('dev.tag', 'dev_ticket_tag_rel', 'ticket_id', 'tag_id', string='Labels')
    story_points = fields.Float('Story Points', tracking=True)
    estimate_hours = fields.Float('Original Estimate', help='Hours.')
    date_deadline = fields.Date('Due Date', tracking=True)
    date_closed = fields.Datetime('Resolved On', readonly=True, copy=False)

    release_id = fields.Many2one('dev.release', 'Release', tracking=True, index='btree_not_null',
                                 domain="[('state', 'not in', ('closed', 'cancelled'))]")
    release_state = fields.Selection(related='release_id.state', string='Release Status')
    feature_id = fields.Many2one('dev.feature', 'Feature', tracking=True, index='btree_not_null')
    repository_id = fields.Many2one('dev.repository', 'Repository', compute='_compute_repository_id', store=True,
                                    readonly=False, tracking=True)
    branch_ids = fields.Many2many('dev.branch', 'dev_branch_ticket_rel', 'ticket_id', 'branch_id',
                                  string='Branches', help='GitHub branches where this ticket is worked on. They are '
                                                          'merged together when the release is shipped.')
    parent_id = fields.Many2one('dev.ticket', 'Parent Ticket', index='btree_not_null', ondelete='cascade',
                                tracking=True)
    child_ids = fields.One2many('dev.ticket', 'parent_id', string='Sub-tasks')
    child_count = fields.Integer('Sub-task Count', compute='_compute_child_count')
    link_ids = fields.One2many('dev.ticket.link', 'source_id', string='Links')
    inverse_link_ids = fields.One2many('dev.ticket.link', 'target_id', string='Linked From')
    is_blocked = fields.Boolean('Blocked', compute='_compute_is_blocked', search='_search_is_blocked',
                                help='Another ticket that blocks this one is still open.')
    criterion_ids = fields.One2many('dev.acceptance.criterion', 'ticket_id', string='Acceptance Criteria',
                                    copy=True)
    criteria_done = fields.Char('Criteria Met', compute='_compute_criteria_done')
    page_ids = fields.Many2many('dev.page', 'dev_page_ticket_rel', 'ticket_id', 'page_id',
                                string='Documentation Pages')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order=stages._order)

    @api.depends('release_id', 'feature_id', 'parent_id')
    def _compute_repository_id(self):
        for ticket in self:
            repository = (ticket.release_id.repository_id or ticket.feature_id.repository_id
                          or ticket.parent_id.repository_id)
            if repository:
                ticket.repository_id = repository

    @api.depends('child_ids')
    def _compute_child_count(self):
        for ticket in self:
            ticket.child_count = len(ticket.child_ids)

    @api.depends('inverse_link_ids.source_id.is_closed', 'inverse_link_ids.link_type_id.is_blocking')
    def _compute_is_blocked(self):
        for ticket in self:
            ticket.is_blocked = any(link.link_type_id.is_blocking and not link.source_id.is_closed
                                    for link in ticket.inverse_link_ids)

    def _search_is_blocked(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('Unsupported search on Blocked.'))
        links = self.env['dev.ticket.link'].search([('link_type_id.is_blocking', '=', True),
                                                    ('source_id.is_closed', '=', False)])
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', links.target_id.ids)]

    @api.depends('criterion_ids.done')
    def _compute_criteria_done(self):
        for ticket in self:
            criteria = ticket.criterion_ids
            ticket.criteria_done = ('%s / %s' % (len(criteria.filtered('done')), len(criteria))) if criteria else ''

    @api.depends('name', 'key')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = '%s %s' % (ticket.key, ticket.name) if ticket.key else ticket.name

    @api.constrains('parent_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError(_('A ticket cannot be a sub-task of itself or of one of its sub-tasks.'))

    @api.onchange('feature_id')
    def _onchange_feature_id(self):
        if self.feature_id.release_id and not self.release_id:
            self.release_id = self.feature_id.release_id

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        if self.parent_id:
            self.release_id = self.release_id or self.parent_id.release_id
            self.feature_id = self.feature_id or self.parent_id.feature_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = self.env['ir.sequence'].sudo().next_by_code('dev.ticket') or False
        tickets = super().create(vals_list)
        tickets.filtered('is_closed').date_closed = fields.Datetime.now()
        return tickets

    def write(self, vals):
        if 'stage_id' in vals:
            stage = self.env['dev.ticket.stage'].browse(vals['stage_id'])
            vals['date_closed'] = fields.Datetime.now() if stage.is_closed else False
            vals.setdefault('kanban_state', 'normal')
        return super().write(vals)

    # ── Buttons ────────────────────────────────────────────────────────────
    def action_assign_to_me(self):
        self.write({'user_id': self.env.user.id})
        return True

    def action_open_children(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(name=_('Sub-tasks'), domain=[('parent_id', '=', self.id)], context={
            'default_parent_id': self.id, 'default_release_id': self.release_id.id,
            'default_feature_id': self.feature_id.id, 'default_repository_id': self.repository_id.id})
        return action

    def _branch_name(self):
        self.ensure_one()
        slug = re.sub(r'[^a-z0-9]+', '-', (self.name or '').lower()).strip('-')[:40].strip('-')
        prefix = (self.type_id.branch_prefix or 'feature').strip('/')
        return '%s/%s%s' % (prefix, self.key or self.id, '-' + slug if slug else '')

    def action_create_branch(self):
        """Create a branch for the ticket on GitHub (from the repository's default branch) and link it."""
        self.ensure_one()
        if not self.repository_id:
            raise UserError(_('Choose the ticket\'s repository (or its release) first.'))
        name = self._branch_name()
        self.repository_id._github_create_branch(name)
        Branch = self.env['dev.branch'].sudo().with_context(active_test=False)
        branch = Branch.search([('repository_id', '=', self.repository_id.id), ('name', '=', name)], limit=1)
        if branch:
            branch.write({'active': True, 'exists_on_github': True})
        else:
            branch = Branch.create({'name': name, 'repository_id': self.repository_id.id, 'exists_on_github': True})
        self.branch_ids = [(4, branch.id)]
        self.message_post(body=_('Branch %s created on GitHub.', name))
        return self.repository_id._notify(_('Branch %s created on GitHub. Check it out with: git fetch && git '
                                            'checkout %s', name, name))

    # ── AI ─────────────────────────────────────────────────────────────────
    def _ai_ticket_criteria_info(self):
        return {
            'title': _('Writing acceptance criteria with AI'),
            'step': _('Asking %(provider)s to write testable acceptance criteria for %(key)s "%(name)s"',
                      provider=self.env['dev.ai']._provider_label(), key=self.key or '', name=self.name),
        }

    def _ai_ticket_criteria(self):
        self.ensure_one()
        context = [_('Ticket (%(type)s): %(name)s', type=self.type_id.name or _('ticket'), name=self.name)]
        if self.description:
            context.append(_('Description:\n%s', html2plaintext(self.description)[:10000]))
        if self.feature_id:
            context.append(_('Part of the feature "%(name)s": %(summary)s', name=self.feature_id.name,
                             summary=self.feature_id.summary or html2plaintext(self.feature_id.description or '')[:3000]))
        if self.criterion_ids:
            context.append(_('Existing criteria (keep, do not repeat):\n%s',
                             '\n'.join('- ' + c.name for c in self.criterion_ids)))
        data = self._ai_json(
            _('Write 3 to 8 testable acceptance criteria for this development ticket, in Given/When/Then form, '
              'covering the main path, edge cases and errors.\n\n%(context)s\n\n'
              'Answer with JSON only: {"acceptance_criteria": ["Given ..., when ..., then ...", ...]}',
              context='\n\n'.join(context)),
            system=_('You are a QA-minded tech lead writing precise acceptance criteria.'), max_tokens=3000)
        criteria = [c.strip() for c in data.get('acceptance_criteria') or [] if isinstance(c, str) and c.strip()]
        if not criteria:
            raise UserError(_('The AI did not return any acceptance criteria. Please try again.'))
        existing = set(self.criterion_ids.mapped('name'))
        start = max(self.criterion_ids.mapped('sequence') or [0])
        self.criterion_ids = [(0, 0, {'name': c, 'sequence': start + i + 1})
                              for i, c in enumerate(criteria) if c not in existing]
        return _('%s acceptance criteria added.', len(criteria))


class DevTicketLink(models.Model):
    _name = 'dev.ticket.link'
    _description = 'Ticket Link'
    _order = 'link_type_id, id'

    source_id = fields.Many2one('dev.ticket', 'Ticket', required=True, ondelete='cascade', index=True)
    link_type_id = fields.Many2one('dev.link.type', 'Relation', required=True, ondelete='restrict',
                                   default=lambda self: self.env['dev.link.type'].search([], limit=1))
    target_id = fields.Many2one('dev.ticket', 'Linked Ticket', required=True, ondelete='cascade', index=True)
    inverse_name = fields.Char(related='link_type_id.inverse_name', string='Relation (inward)')
    target_stage_id = fields.Many2one(related='target_id.stage_id', string='Linked Ticket Stage')
    source_stage_id = fields.Many2one(related='source_id.stage_id', string='Ticket Stage')

    _link_uniq = models.Constraint('UNIQUE (source_id, link_type_id, target_id)', 'These tickets are already linked '
                                                                                  'this way.')

    @api.constrains('source_id', 'target_id')
    def _check_not_self(self):
        for link in self:
            if link.source_id == link.target_id:
                raise ValidationError(_('A ticket cannot be linked to itself.'))

    @api.depends('source_id', 'link_type_id', 'target_id')
    def _compute_display_name(self):
        for link in self:
            link.display_name = '%s %s %s' % (link.source_id.key or '', link.link_type_id.name or '',
                                              link.target_id.key or '')

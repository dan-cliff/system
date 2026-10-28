"""Features: where product design writes up what is to be built.

A feature holds the problem statement, technical specification, acceptance
criteria, supporting research and third-party documentation links, and groups
the tickets that build it.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class DevFeature(models.Model):
    _name = 'dev.feature'
    _description = 'Feature'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dev.ai.mixin']
    _order = 'priority_sequence, sequence, id desc'
    _rec_names_search = ['name', 'key']
    _dev_ai_jobs = ('feature_spec', 'feature_tickets')

    key = fields.Char('Feature Number', readonly=True, copy=False, index=True)
    name = fields.Char('Title', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    stage_id = fields.Many2one('dev.feature.stage', 'Stage', tracking=True, index=True, copy=False,
                               default=lambda self: self.env['dev.feature.stage'].search([], limit=1),
                               group_expand='_read_group_stage_ids', ondelete='restrict')
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True)
    priority_id = fields.Many2one('dev.priority', 'Priority', tracking=True,
                                  default=lambda self: self.env['dev.priority'].search([], offset=2, limit=1))
    priority_sequence = fields.Integer('Priority Order', related='priority_id.sequence', store=True)
    user_id = fields.Many2one('res.users', 'Product Owner', default=lambda self: self.env.user, tracking=True,
                              domain=[('share', '=', False)])
    release_id = fields.Many2one('dev.release', 'Release', tracking=True, index='btree_not_null',
                                 domain="[('state', 'not in', ('closed', 'cancelled'))]")
    repository_id = fields.Many2one('dev.repository', 'Repository', tracking=True,
                                    compute='_compute_repository_id', store=True, readonly=False)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    tag_ids = fields.Many2many('dev.tag', 'dev_feature_tag_rel', 'feature_id', 'tag_id', string='Tags')
    target_date = fields.Date('Target Date', tracking=True)

    summary = fields.Text(help='One or two sentences: who is it for and what does it let them do?')
    description = fields.Html('Problem and Goals',
                              help='The problem the feature solves, who has it, and what success looks like.')
    specification = fields.Html('Technical Specification')
    research = fields.Html('Supporting Research')
    criterion_ids = fields.One2many('dev.acceptance.criterion', 'feature_id', string='Acceptance Criteria',
                                    copy=True)
    link_ids = fields.One2many('dev.feature.link', 'feature_id', string='Documentation Links', copy=True)
    page_ids = fields.Many2many('dev.page', 'dev_page_feature_rel', 'feature_id', 'page_id',
                                string='Documentation Pages')

    ticket_ids = fields.One2many('dev.ticket', 'feature_id', string='Tickets')
    branch_ids = fields.Many2many('dev.branch', 'dev_branch_feature_rel', 'feature_id', 'branch_id',
                                  string='Branches', help='GitHub branches where this feature is built.')
    ticket_count = fields.Integer('Ticket Count', compute='_compute_progress')
    ticket_done_count = fields.Integer('Tickets Done', compute='_compute_progress')
    points_total = fields.Float('Story Points', compute='_compute_progress')
    progress = fields.Float('Progress (%)', compute='_compute_progress')
    criteria_done = fields.Char('Criteria Met', compute='_compute_criteria_done')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order=stages._order)

    @api.depends('release_id')
    def _compute_repository_id(self):
        for feature in self:
            if feature.release_id:
                feature.repository_id = feature.release_id.repository_id

    @api.depends('ticket_ids.is_closed', 'ticket_ids.story_points')
    def _compute_progress(self):
        for feature in self:
            tickets = feature.ticket_ids
            done = tickets.filtered('is_closed')
            feature.ticket_count = len(tickets)
            feature.ticket_done_count = len(done)
            feature.points_total = sum(tickets.mapped('story_points'))
            if feature.points_total:
                feature.progress = 100.0 * sum(done.mapped('story_points')) / feature.points_total
            else:
                feature.progress = 100.0 * len(done) / len(tickets) if tickets else 0.0

    @api.depends('criterion_ids.done')
    def _compute_criteria_done(self):
        for feature in self:
            criteria = feature.criterion_ids
            feature.criteria_done = ('%s / %s' % (len(criteria.filtered('done')), len(criteria))) if criteria else ''

    @api.depends('name', 'key')
    def _compute_display_name(self):
        for feature in self:
            feature.display_name = '%s %s' % (feature.key, feature.name) if feature.key else feature.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = self.env['ir.sequence'].sudo().next_by_code('dev.feature') or False
        return super().create(vals_list)

    def action_open_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dev_management.dev_ticket_action')
        action.update(domain=[('feature_id', '=', self.id)], context={
            'default_feature_id': self.id, 'default_release_id': self.release_id.id,
            'default_repository_id': self.repository_id.id})
        return action

    # ── AI ─────────────────────────────────────────────────────────────────
    def _ai_context(self):
        self.ensure_one()
        lines = [_('Feature: %s', self.name)]
        for label, value in ((_('Summary'), self.summary), (_('Problem and goals'), html2plaintext(self.description or '')),
                             (_('Technical specification'), html2plaintext(self.specification or '')),
                             (_('Supporting research'), html2plaintext(self.research or ''))):
            if value and value.strip():
                lines.append('%s:\n%s' % (label, value.strip()[:15000]))
        if self.criterion_ids:
            lines.append(_('Acceptance criteria:\n%s', '\n'.join('- ' + c.name for c in self.criterion_ids)))
        if self.link_ids:
            lines.append(_('Reference links:\n%s', '\n'.join('- %s %s' % (l.name, l.url or '') for l in self.link_ids)))
        if self.repository_id:
            lines.append(_('Repository: %s', self.repository_id.full_name))
        return '\n\n'.join(lines)

    def _ai_feature_spec_info(self):
        missing = [label for field, label in (('description', _('the problem and goals')),
                                              ('specification', _('a technical specification')),
                                              ('criterion_ids', _('acceptance criteria'))) if not self[field]]
        return {
            'title': _('Drafting the feature with AI'),
            'step': _('Asking %(provider)s to write %(parts)s for "%(name)s"',
                      provider=self.env['dev.ai']._provider_label(), name=self.name,
                      parts=', '.join(missing) if missing else _('an improved specification and acceptance criteria')),
        }

    def _ai_feature_spec(self):
        self.ensure_one()
        data = self._ai_json(
            _('Help a product team design this software feature.\n\n%(context)s\n\n'
              'Write: the problem and goals (who has the problem, why it matters, what success looks like), a '
              'technical specification (approach, data model changes, user interface, integrations, edge cases, '
              'security and performance considerations, open questions) and 4 to 10 testable acceptance '
              'criteria in Given/When/Then form. Build on what is already written rather than contradicting it.\n\n'
              'Answer with JSON only: {"description": "<p>...</p>", "specification": "<h3>...</h3><p>...</p>", '
              '"acceptance_criteria": ["Given ..., when ..., then ...", ...]} using only the HTML tags p, h3, ul, '
              'ol, li, strong, em and code.', context=self._ai_context()),
            system=_('You are a senior product manager and software architect writing clear feature specifications.'),
            max_tokens=8000)
        vals = {}
        if data.get('description'):
            vals['description'] = data['description']
        if data.get('specification'):
            vals['specification'] = data['specification']
        criteria = [c.strip() for c in data.get('acceptance_criteria') or [] if isinstance(c, str) and c.strip()]
        if criteria:
            existing = set(self.criterion_ids.mapped('name'))
            start = max(self.criterion_ids.mapped('sequence') or [0])
            vals['criterion_ids'] = [(0, 0, {'name': c, 'sequence': start + i + 1})
                                     for i, c in enumerate(criteria) if c not in existing]
        if not vals:
            raise UserError(_('The AI did not return a specification. Please try again.'))
        self.write(vals)
        return _('The feature has been drafted: check the Problem and Goals, Specification and Acceptance '
                 'Criteria tabs.')

    def _ai_feature_tickets_info(self):
        return {
            'title': _('Breaking the feature into tickets with AI'),
            'step': _('Asking %(provider)s to split "%(name)s" into development tickets with acceptance criteria '
                      'and story points', provider=self.env['dev.ai']._provider_label(), name=self.name),
        }

    def _ai_feature_tickets(self):
        self.ensure_one()
        types = self.env['dev.ticket.type'].search([])
        existing = '\n'.join('- %s %s' % (t.key, t.name) for t in self.ticket_ids) or _('none')
        data = self._ai_json(
            _('Split this software feature into development tickets a developer can each finish in one to three '
              'days.\n\n%(context)s\n\nTickets that already exist (do not repeat them):\n%(existing)s\n\n'
              'Ticket types: %(types)s.\n\nAnswer with JSON only: {"tickets": [{"name": "short imperative '
              'summary", "type": "one of the ticket types", "story_points": 1|2|3|5|8, "description": '
              '"<p>what to do and how</p>", "acceptance_criteria": ["...", "..."]}]}',
              context=self._ai_context(), existing=existing, types=', '.join(types.mapped('name'))),
            system=_('You are a tech lead who plans work into small, well-described tickets.'),
            max_tokens=8000)
        items = [item for item in data.get('tickets') or [] if isinstance(item, dict) and item.get('name')]
        if not items:
            raise UserError(_('The AI did not suggest any tickets. Please try again.'))
        by_name = {t.name.lower(): t for t in types}
        Ticket = self.env['dev.ticket']
        for item in items:
            criteria = [c for c in item.get('acceptance_criteria') or [] if isinstance(c, str) and c.strip()]
            try:
                points = float(item.get('story_points') or 0)
            except (TypeError, ValueError):
                points = 0.0
            Ticket.create({
                'name': item['name'][:250],
                'type_id': by_name.get((item.get('type') or '').lower(), types[:1]).id,
                'story_points': points,
                'description': item.get('description') or False,
                'feature_id': self.id,
                'release_id': self.release_id.id,
                'repository_id': self.repository_id.id,
                'company_id': self.company_id.id,
                'criterion_ids': [(0, 0, {'name': c.strip(), 'sequence': i}) for i, c in enumerate(criteria)],
            })
        self.message_post(body=Markup('<p>%s</p>') % _('%s ticket(s) suggested by AI were added.', len(items)))
        return _('%s ticket(s) have been created. See the Tickets tab.', len(items))


class DevFeatureLink(models.Model):
    _name = 'dev.feature.link'
    _description = 'Feature Documentation Link'
    _order = 'sequence, id'

    feature_id = fields.Many2one('dev.feature', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Title', required=True)
    url = fields.Char('URL')
    notes = fields.Text()
    file = fields.Binary('File', attachment=True,
                         help='A document to keep with the feature instead of (or as well as) a link.')
    file_name = fields.Char()


class DevAcceptanceCriterion(models.Model):
    _name = 'dev.acceptance.criterion'
    _description = 'Acceptance Criterion'
    _order = 'sequence, id'

    name = fields.Text('Criterion', required=True)
    sequence = fields.Integer(default=10)
    done = fields.Boolean('Met')
    ticket_id = fields.Many2one('dev.ticket', ondelete='cascade', index='btree_not_null')
    feature_id = fields.Many2one('dev.feature', ondelete='cascade', index='btree_not_null')

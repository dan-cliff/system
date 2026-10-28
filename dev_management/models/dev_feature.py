"""Features: where product design writes up what is to be built.

A feature holds the problem statement, technical specification, acceptance
criteria, supporting research and third-party documentation links, and groups
the tickets that build it.
"""
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_sanitize


def _unwrap_paragraph(html):
    """Inline replacement HTML: drop a single wrapping <p>...</p> the AI may have added anyway."""
    match = re.fullmatch(r'\s*<p>(.*)</p>\s*', html or '', re.DOTALL)
    return match.group(1) if match and '<p' not in match.group(1) else html


class DevFeature(models.Model):
    _name = 'dev.feature'
    _description = 'Feature'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dev.ai.mixin']
    _order = 'priority_sequence, sequence, id desc'
    _rec_names_search = ['name', 'key']
    _dev_ai_jobs = ('feature_spec', 'feature_tickets', 'feature_research', 'selection_edit')

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
    ai_spec_drafted = fields.Boolean(
        'Drafted with AI', copy=False,
        help='"Draft with AI" has run: the button becomes "Rerun AI with additional context".')

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
            met = _(' (met)')
            lines.append(_('Acceptance criteria:\n%s', '\n'.join(
                '- %s%s' % (c.name, met if c.done else '') for c in self.criterion_ids)))
        if self.link_ids:
            lines.append(_('Reference links:\n%s', '\n'.join('- %s %s' % (l.name, l.url or '') for l in self.link_ids)))
        if self.repository_id:
            lines.append(_('Repository: %s', self.repository_id.full_name))
        return '\n\n'.join(lines)

    def _ai_feature_spec_info(self, prompt=None, **kwargs):
        provider = self.env['dev.ai']._provider_label()
        if prompt:
            return {
                'title': _('Reworking the feature with AI'),
                'step': _('Asking %(provider)s to rework the problem and goals, technical specification and '
                          'acceptance criteria of "%(name)s" with your additional context',
                          provider=provider, name=self.name),
            }
        missing = [label for field, label in (('description', _('the problem and goals')),
                                              ('specification', _('a technical specification')),
                                              ('criterion_ids', _('acceptance criteria'))) if not self[field]]
        return {
            'title': _('Drafting the feature with AI'),
            'step': _('Asking %(provider)s to write %(parts)s for "%(name)s"', provider=provider, name=self.name,
                      parts=', '.join(missing) if missing else _('an improved specification and acceptance criteria')),
        }

    def _ai_feature_spec(self, prompt=None, **kwargs):
        """Draft with AI, or, with ``prompt``, rework the whole draft with the user's additional context."""
        self.ensure_one()
        answer_format = _(
            'Answer with JSON only: {"description": "<p>...</p>", "specification": "<h3>...</h3><p>...</p>", '
            '"acceptance_criteria": ["Given ..., when ..., then ...", ...]} using only the HTML tags p, h3, ul, '
            'ol, li, strong, em and code.')
        if prompt:
            met = self.criterion_ids.filtered('done')
            request = _(
                'Help a product team rework the design of this software feature.\n\n%(context)s\n\n'
                'Additional context and instructions from the team (follow them):\n%(prompt)s\n\n'
                'Rework the problem and goals, the technical specification and the acceptance criteria with this '
                'context, and return the complete revised versions of all three (not just the changes). Keep what '
                'is still right. Acceptance criteria already met: %(met)s - keep them exactly as written and do not '
                'repeat them in your list.\n\n%(format)s',
                context=self._ai_context(), prompt=prompt.strip()[:8000], format=answer_format,
                met='; '.join(met.mapped('name')) or _('none'))
        else:
            request = _(
                'Help a product team design this software feature.\n\n%(context)s\n\n'
                'Write: the problem and goals (who has the problem, why it matters, what success looks like), a '
                'technical specification (approach, data model changes, user interface, integrations, edge cases, '
                'security and performance considerations, open questions) and 4 to 10 testable acceptance '
                'criteria in Given/When/Then form. Build on what is already written rather than contradicting '
                'it.\n\n%(format)s', context=self._ai_context(), format=answer_format)
        data = self._ai_json(
            request,
            system=_('You are a senior product manager and software architect writing clear feature specifications.'),
            max_tokens=8000)
        vals = {}
        if data.get('description'):
            vals['description'] = data['description']
        if data.get('specification'):
            vals['specification'] = data['specification']
        criteria = [c.strip() for c in data.get('acceptance_criteria') or [] if isinstance(c, str) and c.strip()]
        if criteria:
            if prompt:
                # A rework replaces the criteria not met yet; met ones stay as they are.
                kept = self.criterion_ids.filtered('done')
                commands = [(2, c.id) for c in self.criterion_ids - kept]
            else:
                kept = self.criterion_ids
                commands = []
            existing = set(kept.mapped('name'))
            start = max(kept.mapped('sequence') or [0])
            commands += [(0, 0, {'name': c, 'sequence': start + i + 1})
                         for i, c in enumerate(criteria) if c not in existing]
            vals['criterion_ids'] = commands
        if not vals:
            raise UserError(_('The AI did not return a specification. Please try again.'))
        vals['ai_spec_drafted'] = True
        self.write(vals)
        if prompt:
            return _('The feature has been reworked with your context: check the Problem and Goals, Specification '
                     'and Acceptance Criteria tabs.')
        return _('The feature has been drafted: check the Problem and Goals, Specification and Acceptance '
                 'Criteria tabs.')

    # ── AI research ────────────────────────────────────────────────────────
    def _ai_feature_research_info(self, **kwargs):
        return {
            'title': _('Researching the feature with AI'),
            'step': _('Asking %(provider)s to search the web for documentation, standards, competitors and data '
                      'about "%(name)s", and to suggest what else to research',
                      provider=self.env['dev.ai']._provider_label(), name=self.name),
        }

    def _ai_feature_research(self, **kwargs):
        """Research with AI: findings from the web (with their sources) and suggestions for further research.

        The findings and suggestions are added to Supporting Research; every third-party source the AI used
        is added to the Third-party Documentation tab. Sources the AI names but didn't actually get from its
        searches are left out.
        """
        self.ensure_one()
        result = self.env['dev.ai']._research(
            _('Research this software feature for its product team.\n\n%(context)s\n\n'
              'Search the web for what helps design and build it: third-party and API documentation, standards '
              'and regulations, how competitors or well-known products do it, best practices, and relevant '
              'data or studies. Then write:\n'
              '1. Findings: what you found that matters for this feature, each with the source it came from.\n'
              '2. Research suggestions: open questions still to answer and how to answer them (user interviews, '
              'data to gather, experiments, products to review).\n\n'
              'End your answer with JSON only, in this form: {"findings_html": "<ul><li>...</li></ul>", '
              '"suggestions_html": "<ul><li>...</li></ul>", "sources": [{"title": "...", "url": "https://...", '
              '"why": "what it is useful for"}]} using only the HTML tags p, h4, ul, ol, li, strong, em, code '
              'and a. List in "sources" only pages you actually read in your searches.',
              context=self._ai_context()),
            system=_('You are a meticulous product researcher. You cite real sources and never invent links.'))
        data = self.env['dev.ai']._parse_json(result['text'], 'findings_html')
        if not isinstance(data, dict) or not (data.get('findings_html') or data.get('suggestions_html')):
            raise UserError(_('The AI research could not be understood. Please try again.'))
        sources = self._ai_research_sources(data.get('sources'), result)
        today = fields.Date.context_today(self).strftime('%d/%m/%Y')
        section = Markup('<h3>%s</h3>') % _('AI research (%s)', today)
        if not result['searched']:
            section += Markup('<p><em>%s</em></p>') % _(
                'Web search was not available, so these findings come from the AI\'s own knowledge and have no '
                'sources. Check them before relying on them.')
        if data.get('findings_html'):
            section += Markup('<h4>%s</h4>') % _('Findings') + html_sanitize(data['findings_html'])
        if data.get('suggestions_html'):
            section += Markup('<h4>%s</h4>') % _('Research suggestions') + html_sanitize(data['suggestions_html'])
        if sources:
            section += Markup('<h4>%s</h4><ul>%s</ul>') % (_('Sources'), Markup('').join(
                Markup('<li><a href="%s" target="_blank">%s</a></li>') % (src['url'], src['title'])
                for src in sources))
        existing_urls = set(self.link_ids.mapped('url'))
        new_links = [src for src in sources if src['url'] not in existing_urls]
        start = max(self.link_ids.mapped('sequence') or [0])
        self.write({
            'research': (self.research or Markup('')) + section,
            'link_ids': [(0, 0, {
                'name': src['title'][:200],
                'url': src['url'],
                'sequence': start + i + 1,
                'notes': _('%(why)sFound by AI research on %(date)s.',
                           why=(src['why'] + ' ') if src.get('why') else '', date=today),
            }) for i, src in enumerate(new_links)],
        })
        return _('Research added to the Research tab, with %s new source(s) in Third-party Documentation.',
                 len(new_links))

    @api.model
    def _ai_research_sources(self, listed, result):
        """The sources to keep: those the AI listed and actually found, then any others its answer cited."""
        found = result['found']
        sources, seen = [], set()
        for item in listed or []:
            if not isinstance(item, dict):
                continue
            url = (item.get('url') or '').strip()
            if url in found and url not in seen:
                seen.add(url)
                sources.append({'url': url, 'title': (item.get('title') or found[url] or url).strip(),
                                'why': (item.get('why') or '').strip()})
        for url in result['cited']:
            if url not in seen:
                seen.add(url)
                sources.append({'url': url, 'title': found.get(url) or url, 'why': ''})
        return sources

    # ── AI selection edits ─────────────────────────────────────────────────
    # Fields where text can be selected and reworked with AI; for a list of lines, the line's text field.
    _dev_ai_selection_fields = {
        'summary': None,
        'description': None,
        'specification': None,
        'research': None,
        'criterion_ids': 'name',
    }

    def _ai_selection_target(self, field, subfield=None):
        if field not in self._dev_ai_selection_fields or self._dev_ai_selection_fields[field] != (subfield or None):
            raise UserError(_('This text can\'t be reworked with AI.'))
        model_field = self._fields[field]
        if subfield:
            return model_field, self.env[model_field.comodel_name]._fields[subfield]
        return model_field, model_field

    def _ai_selection_edit_info(self, field=None, subfield=None, **kwargs):
        parent, target = self._ai_selection_target(field, subfield)
        label = parent.get_description(self.env)['string']
        return {
            'title': _('Reworking the selected text with AI'),
            'step': _('Asking %(provider)s to rework the text you selected in %(field)s, as you asked',
                      provider=self.env['dev.ai']._provider_label(), field=label),
        }

    def _ai_selection_edit(self, field=None, subfield=None, prompt='', selected_text='', before='', after='',
                           is_html=False, multi_block=False, old_value=None, start=None, end=None, **kwargs):
        """Rework the selected passage of a field as the user asked.

        HTML fields: returns {'html': replacement} for the form to put in place of the selection.
        Text fields and lines: ``old_value`` with the ``start``/``end`` of the selection identifies the text;
        the replacement is written here.
        """
        self.ensure_one()
        parent, target = self._ai_selection_target(field, subfield)
        if not (prompt or '').strip() or not (selected_text or '').strip():
            raise UserError(_('Select some text and say what the AI should do with it.'))
        html = bool(is_html) and target.type == 'html'
        if html:
            fmt = (_('Return HTML using only the tags p, h3, ul, ol, li, strong, em, code and a, because the '
                     'selection spans several paragraphs or list items.') if multi_block else
                   _('Return the replacement as inline HTML only (no p, list or heading tags; you may use strong, '
                     'em, code, a and br), because it goes inside an existing paragraph.'))
        else:
            fmt = _('Return plain text only, with no markdown or HTML.')
        data = self._ai_json(
            _('You are helping a product team edit the "%(field)s" of a software feature.\n\n'
              'The whole feature, for context:\n%(context)s\n\n'
              'Text just before the selection:\n"""%(before)s"""\n\n'
              'The selected text to rework:\n"""%(selected)s"""\n\n'
              'Text just after the selection:\n"""%(after)s"""\n\n'
              'Instruction from the team: %(prompt)s\n\n'
              'Rewrite only the selected text so it follows the instruction and still reads naturally with the '
              'text around it. %(format)s\n\nAnswer with JSON only: {"replacement": "..."}',
              field=parent.get_description(self.env)['string'], context=self._ai_context(),
              before=(before or '')[-2000:], selected=(
                  kwargs.get('selected_html') if html and kwargs.get('selected_html') else selected_text)[:20000],
              after=(after or '')[:1000], prompt=prompt.strip()[:4000], format=fmt),
            system=_('You are an expert technical editor. You change only what you are asked to change.'),
            max_tokens=8000)
        replacement = data.get('replacement')
        if not isinstance(replacement, str) or not replacement.strip():
            raise UserError(_('The AI did not return a replacement. Please try again.'))
        if html:
            replacement = html_sanitize(replacement)
            if not multi_block:
                replacement = _unwrap_paragraph(replacement)
            return {'html': replacement, 'message': _('The selected text has been reworked.')}
        return self._ai_selection_write_text(field, subfield, old_value, start, end, replacement.strip())

    def _ai_selection_write_text(self, field, subfield, old_value, start, end, replacement):
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            raise UserError(_('The selection was lost. Select the text again.'))
        old_value = old_value or ''
        if not 0 <= start < end <= len(old_value):
            raise UserError(_('The selection was lost. Select the text again.'))
        new_value = old_value[:start] + replacement + old_value[end:]
        if subfield:
            line = self[field].filtered(lambda l: (l[subfield] or '') == old_value)[:1]
            if not line:
                raise UserError(_('That text changed while the AI was working. Select it again.'))
            line[subfield] = new_value
        else:
            if (self[field] or '') != old_value:
                raise UserError(_('That text changed while the AI was working. Select it again.'))
            self[field] = new_value
        return _('The selected text has been reworked.')

    def _ai_feature_tickets_info(self, **kwargs):
        return {
            'title': _('Breaking the feature into tickets with AI'),
            'step': _('Asking %(provider)s to split "%(name)s" into development tickets with acceptance criteria '
                      'and story points', provider=self.env['dev.ai']._provider_label(), name=self.name),
        }

    def _ai_feature_tickets(self, **kwargs):
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

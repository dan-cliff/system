"""Feature suggestions, like Microsoft User Voice or Productboard.

Customers (on the website forum) and colleagues (in the backend, or from the
Helpdesk) post ideas, vote on them with how important they are and why, and
discuss them. The product team moderates them (status, official response,
merging duplicates), links them to the Features and Tickets that deliver them
and turns the best into Features. When a release that delivers a suggestion
reaches Core Release, the suggestion is marked released and its voters hear
about it.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

# Changing these needs the "Feature Suggestions: Moderate" permission.
MODERATED_FIELDS = {'status_id', 'is_published', 'website_published', 'official_response', 'merged_into_id'}


class DevSuggestion(models.Model):
    _name = 'dev.suggestion'
    _description = 'Feature Suggestion'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'website.published.mixin', 'dev.ai.mixin']
    _order = 'score desc, vote_count desc, id desc'
    _rec_names_search = ['name', 'ref']
    _dev_ai_jobs = ('suggestion_triage',)

    ref = fields.Char('Reference', readonly=True, copy=False, index=True)
    name = fields.Char('Title', required=True, tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    partner_id = fields.Many2one('res.partner', 'Suggested By', tracking=True, index='btree_not_null',
                                 default=lambda self: self.env.user.partner_id)
    user_id = fields.Many2one('res.users', 'Owner', tracking=True, domain=[('share', '=', False)],
                              help='The product manager looking after this suggestion.')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    category_id = fields.Many2one('dev.suggestion.category', 'Category', tracking=True, index=True)
    status_id = fields.Many2one('dev.suggestion.status', 'Status', tracking=True, index=True, copy=False,
                                default=lambda self: self.env['dev.suggestion.status'].search([], limit=1),
                                group_expand='_read_group_status_ids', ondelete='restrict')
    status_closed = fields.Boolean(related='status_id.is_closed', string='Closed for Votes')
    source_id = fields.Many2one('dev.suggestion.source', 'Source', tracking=True)
    vote_ids = fields.One2many('dev.suggestion.vote', 'suggestion_id', string='Votes')
    vote_count = fields.Integer('Vote Count', compute='_compute_votes', store=True)
    score = fields.Integer('Score', compute='_compute_votes', store=True,
                           help='Sum of the votes weighted by how important they are to the voters.')
    comment_count = fields.Integer('Comments', compute='_compute_comment_count')
    voted = fields.Boolean('Voted', compute='_compute_voted', help='The current user has voted for it.')
    official_response = fields.Html('Official Response', tracking=True,
                                    help='The product team\'s answer, shown at the top of the suggestion on the website.')
    response_user_id = fields.Many2one('res.users', 'Answered By', readonly=True, copy=False)
    response_date = fields.Datetime('Answered On', readonly=True, copy=False)
    merged_into_id = fields.Many2one('dev.suggestion', 'Merged Into', tracking=True, copy=False,
                                     index='btree_not_null',
                                     help='This suggestion duplicates another: its votes were moved there.')
    merged_ids = fields.One2many('dev.suggestion', 'merged_into_id', string='Merged Duplicates')
    feature_ids = fields.Many2many('dev.feature', 'dev_suggestion_feature_rel', 'suggestion_id', 'feature_id',
                                   string='Features', help='The features that deliver this suggestion.')
    ticket_ids = fields.Many2many('dev.ticket', 'dev_suggestion_ticket_rel', 'suggestion_id', 'ticket_id',
                                  string='Tickets', help='The development tickets that deliver this suggestion.')
    release_ids = fields.Many2many('dev.release', compute='_compute_release_ids', string='Releases')
    released_in_id = fields.Many2one('dev.release', 'Released In', readonly=True, copy=False)
    # AI triage
    ai_summary = fields.Text('AI Summary', readonly=True, copy=False)
    similar_suggestion_ids = fields.Many2many(
        'dev.suggestion', 'dev_suggestion_similar_rel', 'suggestion_id', 'similar_id', string='Possible Duplicates',
        readonly=True, copy=False)
    suggested_feature_ids = fields.Many2many(
        'dev.feature', 'dev_suggestion_ai_feature_rel', 'suggestion_id', 'feature_id',
        string='Related Features (AI)', readonly=True, copy=False)
    can_moderate = fields.Boolean(compute='_compute_can_moderate')

    @api.model
    def _read_group_status_ids(self, statuses, domain):
        return statuses.search([], order=statuses._order)

    @api.depends('vote_ids.importance_id.weight')
    def _compute_votes(self):
        for suggestion in self:
            suggestion.vote_count = len(suggestion.vote_ids)
            suggestion.score = sum(vote.importance_id.weight or 1 for vote in suggestion.vote_ids)

    def _compute_comment_count(self):
        comment = self.env.ref('mail.mt_comment')
        counts = dict(self.env['mail.message'].sudo()._read_group(
            [('model', '=', self._name), ('res_id', 'in', self.ids), ('message_type', '=', 'comment'),
             ('subtype_id', '=', comment.id)], ['res_id'], ['__count']))
        for suggestion in self:
            suggestion.comment_count = counts.get(suggestion.id, 0)

    @api.depends('vote_ids.partner_id')
    @api.depends_context('uid')
    def _compute_voted(self):
        partner = self.env.user.partner_id
        voted = set(self.env['dev.suggestion.vote'].sudo().search([
            ('suggestion_id', 'in', self.ids), ('partner_id', '=', partner.id)]).suggestion_id.ids)
        for suggestion in self:
            suggestion.voted = suggestion.id in voted

    @api.depends('feature_ids.release_id', 'ticket_ids.release_id')
    def _compute_release_ids(self):
        for suggestion in self:
            suggestion.release_ids = suggestion.feature_ids.release_id | suggestion.ticket_ids.release_id

    @api.depends_context('uid')
    def _compute_can_moderate(self):
        can = self._user_can_moderate()
        for suggestion in self:
            suggestion.can_moderate = can

    @api.depends_context('uid')
    def _compute_can_publish(self):
        can = self._user_can_moderate()
        for suggestion in self:
            suggestion.can_publish = can

    def _get_can_publish_error_message(self):
        return _('You need the "Feature Suggestions: Moderate" permission to publish suggestions.')

    @api.model
    def _user_can_moderate(self):
        return self.env.su or self.env.user.has_group('dev_feature_suggestions.group_dev_suggestion_moderate')

    def _compute_website_url(self):
        for suggestion in self:
            suggestion.website_url = '/feature-requests/%s' % suggestion.id if suggestion.id else '#'

    @api.depends('name', 'ref')
    def _compute_display_name(self):
        for suggestion in self:
            suggestion.display_name = '%s %s' % (suggestion.ref, suggestion.name) if suggestion.ref else suggestion.name

    # ── CRUD ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        publish = []
        for vals in vals_list:
            if not vals.get('ref'):
                vals['ref'] = self.env['ir.sequence'].sudo().next_by_code('dev.suggestion') or False
            requested = vals.pop('is_published', None)
            requested = vals.pop('website_published', requested)
            if requested and not self._user_can_moderate():
                raise AccessError(self._get_can_publish_error_message())
            publish.append(self._auto_publish() if requested is None else bool(requested))
        suggestions = super().create(vals_list)
        # New suggestions are published automatically (Settings), whoever posts them.
        suggestions.filtered(lambda s: publish[suggestions.ids.index(s.id)]).sudo().is_published = True
        for suggestion in suggestions.filtered('partner_id'):
            suggestion.message_subscribe(partner_ids=suggestion.partner_id.ids)
        return suggestions

    @api.model
    def _auto_publish(self):
        return not self.env['ir.config_parameter'].sudo().get_param('dev_feature_suggestions.review_first')

    def write(self, vals):
        moderated = MODERATED_FIELDS & set(vals)
        if moderated and not self._user_can_moderate():
            raise AccessError(_('You need the "Feature Suggestions: Moderate" permission to change the status, '
                                'publish, answer or merge suggestions.'))
        if vals.get('official_response'):
            vals.setdefault('response_user_id', self.env.uid)
            vals.setdefault('response_date', fields.Datetime.now())
        old_status = {s.id: s.status_id for s in self} if 'status_id' in vals else {}
        result = super().write(vals)
        if 'status_id' in vals:
            for suggestion in self.filtered(lambda s: s.status_id != old_status.get(s.id)):
                suggestion._announce_status()
        return result

    def _announce_status(self):
        """Tell the followers (the suggester and every voter) about the new status."""
        self.ensure_one()
        status = self.status_id
        if not status.notify_followers:
            return
        body = Markup('<p>%s</p>') % _('Status changed to %s.', status.name)
        if status.website_description:
            body += Markup('<p>%s</p>') % status.website_description
        self.message_post(body=body, subtype_xmlid='mail.mt_comment', message_type='comment')

    # ── Voting ─────────────────────────────────────────────────────────────
    def _add_vote(self, partner, importance=None, note=None, source=None):
        """Add (or update) ``partner``'s vote. Voters follow the suggestion. Works for any reader (sudo)."""
        self.ensure_one()
        target = self.merged_into_id or self
        if target.status_id.is_closed:
            raise UserError(_('Voting is closed for this suggestion (%s).', target.status_id.name))
        Vote = self.env['dev.suggestion.vote'].sudo()
        vote = Vote.search([('suggestion_id', '=', target.id), ('partner_id', '=', partner.id)], limit=1)
        vals = {}
        if importance:
            vals['importance_id'] = importance.id
        if note:
            vals['note'] = note
        if source:
            vals['source_id'] = source.id
        if vote:
            vote.write(vals)
        else:
            vote = Vote.create(dict(vals, suggestion_id=target.id, partner_id=partner.id))
        target.sudo().message_subscribe(partner_ids=partner.ids)
        return vote

    def _remove_vote(self, partner):
        self.ensure_one()
        self.env['dev.suggestion.vote'].sudo().search([
            ('suggestion_id', '=', self.id), ('partner_id', '=', partner.id)]).unlink()

    def action_vote(self):
        """Vote (or remove the vote) as the current user."""
        self.check_access('read')
        for suggestion in self:
            if suggestion.voted:
                suggestion._remove_vote(self.env.user.partner_id)
            else:
                suggestion._add_vote(self.env.user.partner_id, source=self.env.ref(
                    'dev_feature_suggestions.source_internal', raise_if_not_found=False))
        return True

    # ── Moderation ─────────────────────────────────────────────────────────
    def _check_moderate(self):
        if not self._user_can_moderate():
            raise AccessError(_('You need the "Feature Suggestions: Moderate" permission to do this.'))

    def action_merge_into(self, target=None):
        """Merge this duplicate into ``target`` (or its first possible duplicate): its votes move there."""
        self._check_moderate()
        self.ensure_one()
        target = target or self.similar_suggestion_ids[:1]
        if not target or target == self:
            raise UserError(_('Choose the suggestion to merge this one into.'))
        for vote in self.sudo().vote_ids:
            if target.vote_ids.filtered(lambda v: v.partner_id == vote.partner_id):
                vote.unlink()
            else:
                vote.suggestion_id = target
        target.sudo().message_subscribe(partner_ids=self.message_partner_ids.ids)
        target.sudo().write({'feature_ids': [(4, f.id) for f in self.feature_ids],
                             'ticket_ids': [(4, t.id) for t in self.ticket_ids]})
        merged_status = self.env.ref('dev_feature_suggestions.status_merged', raise_if_not_found=False)
        self.sudo().write({'merged_into_id': target.id, 'status_id': (merged_status or self.status_id).id,
                           'is_published': False})
        self.message_post(body=_('Merged into %s; its votes now count there.', target.display_name))
        target.message_post(body=_('%s was merged into this suggestion.', self.display_name))
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.suggestion', 'res_id': target.id,
                'view_mode': 'form'}

    def action_create_feature(self):
        """Turn the suggestion into a Feature for the product team to design."""
        self._check_moderate()
        self.ensure_one()
        feature = self.env['dev.feature'].create({
            'name': self.name,
            'summary': html2plaintext(self.description or '')[:500] or False,
            'description': self.description,
            'company_id': self.company_id.id,
        })
        self.write({'feature_ids': [(4, feature.id)]})
        planned = self.env.ref('dev_feature_suggestions.status_planned', raise_if_not_found=False)
        if planned and not self.status_id.is_closed and self.status_id.sequence < planned.sequence:
            self.status_id = planned
        feature.message_post(body=_('Created from the feature suggestion %(name)s (%(votes)s votes).',
                                    name=self.display_name, votes=self.vote_count))
        return {'type': 'ir.actions.act_window', 'res_model': 'dev.feature', 'res_id': feature.id,
                'view_mode': 'form'}

    def action_open_votes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Votes'),
            'res_model': 'dev.suggestion.vote',
            'view_mode': 'list,form',
            'domain': [('suggestion_id', '=', self.id)],
            'context': {'default_suggestion_id': self.id},
        }

    def _mark_released(self, release):
        """Called when a release that delivers these suggestions reaches Core Release."""
        status = self.env['dev.suggestion.status'].search([('set_on_release', '=', True)], limit=1)
        for suggestion in self.sudo().filtered(lambda s: not s.merged_into_id and not s.released_in_id):
            vals = {'released_in_id': release.id}
            if status:
                vals['status_id'] = status.id
            suggestion.write(vals)
            suggestion.message_post(
                body=Markup('<p>%s</p>') % _('Released in %s. Thank you for your suggestion!', release.display_name),
                subtype_xmlid='mail.mt_comment', message_type='comment')

    # ── AI ─────────────────────────────────────────────────────────────────
    def _ai_suggestion_triage_info(self):
        return {
            'title': _('Triaging the suggestion with AI'),
            'step': _('Asking %(provider)s to summarise "%(name)s", suggest a category and look for duplicates '
                      'among %(suggestions)s suggestions and %(features)s features',
                      provider=self.env['dev.ai']._provider_label(), name=self.name,
                      suggestions=self.search_count([('id', '!=', self.id), ('merged_into_id', '=', False)]),
                      features=self.env['dev.feature'].search_count([])),
        }

    def _ai_suggestion_triage(self):
        self.ensure_one()
        others = self.search([('id', '!=', self.id), ('merged_into_id', '=', False)], limit=400)
        features = self.env['dev.feature'].search([], limit=400)
        categories = self.env['dev.suggestion.category'].search([])
        votes = '\n'.join('- %s%s' % (v.importance_id.name or '', ': ' + v.note if v.note else '')
                          for v in self.vote_ids if v.note)[:5000]
        data = self._ai_json(
            _('Triage this product feature suggestion.\n\nSuggestion: %(name)s\n%(description)s\n\n'
              'What voters said:\n%(votes)s\n\nCategories: %(categories)s\n\n'
              'Other suggestions (id: title):\n%(others)s\n\nExisting features (id: title):\n%(features)s\n\n'
              'Answer with JSON only: {"summary": "two or three sentences: the need behind it and who has it", '
              '"category": "one of the categories or empty", "duplicate_ids": [ids of other suggestions asking '
              'for the same thing], "feature_ids": [ids of existing features that would deliver it]}',
              name=self.name, description=html2plaintext(self.description or '')[:8000], votes=votes or _('none'),
              categories=', '.join(categories.mapped('name')) or _('none'),
              others='\n'.join('%s: %s' % (s.id, s.name) for s in others) or _('none'),
              features='\n'.join('%s: %s' % (f.id, f.name) for f in features) or _('none')),
            system=_('You are a product manager who triages customer feedback carefully and never invents ids.'),
            max_tokens=2000)

        def ids(key, records):
            wanted = set()
            for value in data.get(key) or []:
                try:
                    wanted.add(int(value))
                except (TypeError, ValueError):
                    continue
            return records.filtered(lambda r: r.id in wanted)

        vals = {
            'ai_summary': (data.get('summary') or '').strip() or False,
            'similar_suggestion_ids': [(6, 0, ids('duplicate_ids', others).ids)],
            'suggested_feature_ids': [(6, 0, ids('feature_ids', features).ids)],
        }
        category = categories.filtered(lambda c: c.name.lower() == (data.get('category') or '').strip().lower())[:1]
        if category and not self.category_id:
            vals['category_id'] = category.id
        self.sudo().write(vals)
        found = len(self.similar_suggestion_ids)
        return _('Triage done: %(dupes)s possible duplicate(s) and %(features)s related feature(s). See the AI '
                 'Triage tab.', dupes=found, features=len(self.suggested_feature_ids))

    def action_link_suggested_features(self):
        self.write({'feature_ids': [(4, f.id) for f in self.suggested_feature_ids]})
        return True


class DevSuggestionVote(models.Model):
    _name = 'dev.suggestion.vote'
    _description = 'Feature Suggestion Vote'
    _order = 'create_date desc, id desc'

    suggestion_id = fields.Many2one('dev.suggestion', 'Suggestion', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', 'Voter', required=True, index=True,
                                 default=lambda self: self.env.user.partner_id)
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', string='Customer',
                                            store=True)
    importance_id = fields.Many2one('dev.suggestion.importance', 'Importance',
                                    default=lambda self: self.env['dev.suggestion.importance'].search([], limit=1))
    weight = fields.Integer(related='importance_id.weight', store=True)
    note = fields.Text('Why It Matters', help='What the voter needs it for (a customer insight).')
    source_id = fields.Many2one('dev.suggestion.source', 'Source')
    company_id = fields.Many2one(related='suggestion_id.company_id', store=True)

    _vote_uniq = models.Constraint('UNIQUE (suggestion_id, partner_id)', 'This person has already voted for it.')

    @api.depends('suggestion_id', 'partner_id')
    def _compute_display_name(self):
        for vote in self:
            vote.display_name = '%s: %s' % (vote.partner_id.display_name or '', vote.suggestion_id.name or '')

    @api.model_create_multi
    def create(self, vals_list):
        votes = super().create(vals_list)
        for vote in votes:
            vote.suggestion_id.sudo().message_subscribe(partner_ids=vote.partner_id.ids)
        return votes
